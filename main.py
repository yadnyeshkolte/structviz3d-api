from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import trimesh
import uuid
import io
import base64
import numpy as np
import struct
from typing import Dict, Any

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development. Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def stl_to_gltf_custom(stl_bytes: bytes, is_binary: bool = False) -> Dict[str, Any]:
    """
    Custom implementation for converting STL to GLTF/GLB using direct binary manipulation.

    Args:
        stl_bytes: Byte content of STL file
        is_binary: If True, create GLB file; otherwise create GLTF representation

    Returns:
        Dictionary with converted file content and metadata
    """
    header_bytes = 80
    unsigned_long_int_bytes = 4
    float_bytes = 4
    vec3_bytes = 4 * 3
    spacer_bytes = 2

    vertices = {}
    indices = []

    # Use BytesIO for in-memory processing
    with io.BytesIO(stl_bytes) as f:
        f.seek(header_bytes)  # skip 80 bytes headers

        num_faces_bytes = f.read(unsigned_long_int_bytes)
        number_faces = struct.unpack("<I", num_faces_bytes)[0]

        # Basic file size validation
        stl_assume_bytes = header_bytes + unsigned_long_int_bytes + number_faces * (
                vec3_bytes * 3 + spacer_bytes + vec3_bytes)
        if stl_assume_bytes > len(stl_bytes):
            raise ValueError("STL file is not binary or is ill-formatted")

        minx, maxx = [9999999, -9999999]
        miny, maxy = [9999999, -9999999]
        minz, maxz = [9999999, -9999999]

        vertices_length_counter = 0

        # Read entire binary data
        data = struct.unpack("<" + "12fH" * number_faces, f.read())
        len_data = len(data)

        for i in range(0, len_data, 13):
            for j in range(3, 12, 3):
                x, y, z = data[i + j:i + j + 3]

                # Precision control
                x = round(x, 5)
                y = round(y, 5)
                z = round(z, 5)

                tuple_xyz = (x, y, z)

                try:
                    indices.append(vertices[tuple_xyz])
                except KeyError:
                    vertices[tuple_xyz] = vertices_length_counter
                    vertices_length_counter += 1
                    indices.append(vertices[tuple_xyz])

                # Update bounding box
                minx = min(minx, x)
                maxx = max(maxx, x)
                miny = min(miny, y)
                maxy = max(maxy, y)
                minz = min(minz, z)
                maxz = max(maxz, z)

    number_vertices = len(vertices)
    vertices_bytelength = number_vertices * vec3_bytes
    unpadded_indices_bytelength = len(indices) * unsigned_long_int_bytes
    indices_bytelength = (unpadded_indices_bytelength + 3) & ~3

    out_bin_bytelength = vertices_bytelength + indices_bytelength

    # GLTF JSON Template
    gltf2 = {
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{
            "primitives": [{
                "attributes": {"POSITION": 1},
                "indices": 0
            }]
        }],
        "buffers": [{
            "byteLength": out_bin_bytelength
        }],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": indices_bytelength,
                "target": 34963  # ELEMENT_ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": indices_bytelength,
                "byteLength": vertices_bytelength,
                "target": 34962  # ARRAY_BUFFER
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5125,  # UNSIGNED_INT
                "count": len(indices),
                "type": "SCALAR",
                "max": [number_vertices - 1],
                "min": [0]
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5126,  # FLOAT
                "count": number_vertices,
                "type": "VEC3",
                "min": [minx, miny, minz],
                "max": [maxx, maxy, maxz]
            }
        ],
        "asset": {"version": "2.0"}
    }

    # Prepare output binary data
    glb_out = bytearray()

    # Prepare vertices data
    reversed_vertices = dict((v, k) for k, v in vertices.items())
    vertices_list = [reversed_vertices[i] for i in range(number_vertices)]
    flattened_vertices = [coord for vertex in vertices_list for coord in vertex]

    # Write indices
    glb_out.extend(struct.pack('<%dI' % len(indices), *indices))

    # Padding for indices
    for _ in range(indices_bytelength - unpadded_indices_bytelength):
        glb_out.extend(b' ')

    # Write vertices
    glb_out.extend(struct.pack('%df' % (number_vertices * 3), *flattened_vertices))

    # Prepare return object
    if is_binary:
        # GLB file with combined JSON and binary data
        gltf_json = str(gltf2).replace("'", '"')
        glb_file = _create_glb_file(gltf_json.encode(), glb_out)

        return {
            "file_content": base64.b64encode(glb_file).decode('utf-8'),
            "filename": f"{uuid.uuid4()}.glb",
            "method": "custom-glb"
        }
    else:
        # Separate GLTF and BIN files
        return {
            "gltf_content": base64.b64encode(str(gltf2).encode()).decode('utf-8'),
            "bin_content": base64.b64encode(glb_out).decode('utf-8'),
            "filename": f"{uuid.uuid4()}.gltf",
            "method": "custom"
        }


def _create_glb_file(json_chunk: bytes, bin_chunk: bytes) -> bytes:
    """
    Create a GLB file with JSON and binary chunks
    """
    # Pad chunks to 4-byte alignment
    json_chunk_padded = json_chunk + b' ' * ((4 - len(json_chunk) % 4) % 4)
    bin_chunk_padded = bin_chunk + b' ' * ((4 - len(bin_chunk) % 4) % 4)

    # GLB file header
    glb_header = struct.pack('<I', 0x46546C67)  # magic: glTF
    glb_header += struct.pack('<I', 2)  # version: 2
    glb_header += struct.pack('<I',
                              12 +  # header size
                              8 + len(json_chunk_padded) +  # JSON chunk
                              8 + len(bin_chunk_padded)  # Binary chunk
                              )

    # JSON chunk
    json_chunk_header = struct.pack('<I', len(json_chunk_padded))
    json_chunk_header += struct.pack('<I', 0x4E4F534A)  # JSON type

    # Binary chunk
    bin_chunk_header = struct.pack('<I', len(bin_chunk_padded))
    bin_chunk_header += struct.pack('<I', 0x004E4942)  # BIN type

    # Combine all parts
    glb_file = (
            glb_header +
            json_chunk_header + json_chunk_padded +
            bin_chunk_header + bin_chunk_padded
    )

    return glb_file


@app.post("/api/convert-stl")
async def convert_stl_to_gltf(
        file: UploadFile = File(...),
        method: str = "trimesh"
):
    """
    Convert STL file to GLTF/GLB format
    """
    # Validate file
    if not file.filename.lower().endswith('.stl'):
        raise HTTPException(status_code=400, detail="Only STL files are accepted")

    # Read file content
    stl_bytes = await file.read()

    # File size limit (10MB)
    if len(stl_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB.")

    try:
        if method.lower() == "trimesh":
            # In-memory conversion with trimesh
            mesh = trimesh.load_mesh(io.BytesIO(stl_bytes))

            # Convert to bytes
            output = io.BytesIO()
            mesh.export(output, file_type='gltf')
            gltf_content = output.getvalue()

            return {
                "method": "trimesh",
                "filename": f"{uuid.uuid4()}.gltf",
                "file_content": base64.b64encode(gltf_content).decode('utf-8')
            }

        elif method.lower() == "custom":
            # Custom conversion method
            return stl_to_gltf_custom(stl_bytes, is_binary=False)

        elif method.lower() == "custom-glb":
            # Custom GLB conversion
            return stl_to_gltf_custom(stl_bytes, is_binary=True)

        else:
            raise HTTPException(status_code=400, detail="Invalid conversion method")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.get("/api/conversion-methods")
async def get_conversion_methods():
    """
    Get information about available conversion methods
    """
    return {
        "methods": [
            {
                "id": "trimesh",
                "name": "Trimesh",
                "description": "Uses Trimesh library for standard conversions",
                "output_format": "GLTF"
            },
            {
                "id": "custom",
                "name": "Custom Implementation",
                "description": "Advanced binary conversion algorithm",
                "output_format": "GLTF + BIN"
            },
            {
                "id": "custom-glb",
                "name": "Custom GLB Implementation",
                "description": "Produces single binary GLB file",
                "output_format": "GLB"
            }
        ]
    }