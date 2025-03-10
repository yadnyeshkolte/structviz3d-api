import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import tempfile
import uuid
import shutil
import trimesh
import numpy as np
import json
import base64
import struct
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # This allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create temporary directory for file storage
TEMP_DIR = os.path.join(os.getcwd(), 'public', 'temp_files')
os.makedirs(TEMP_DIR, exist_ok=True)


def stl_to_gltf_custom(binary_stl_path: str, out_path: str, is_binary: bool = False) -> Dict[str, str]:
    """
    Custom implementation for converting STL to GLTF/GLB using direct binary manipulation.

    Args:
        binary_stl_path: Path to the input STL file
        out_path: Directory path for output files or full path for GLB file
        is_binary: If True, create GLB file; otherwise create GLTF + BIN files

    Returns:
        Dictionary with file paths information
    """
    header_bytes = 80
    unsigned_long_int_bytes = 4
    float_bytes = 4
    vec3_bytes = 4 * 3
    spacer_bytes = 2
    num_vertices_in_face = 3

    vertices = {}
    indices = []

    # Determine output paths
    if not is_binary:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        out_bin = os.path.join(out_path, "out.bin")
        out_gltf = os.path.join(out_path, "out.gltf")
    else:
        out_bin = out_path

    with open(binary_stl_path, "rb") as f:
        f.seek(header_bytes)  # skip 80 bytes headers

        num_faces_bytes = f.read(unsigned_long_int_bytes)
        number_faces = struct.unpack("<I", num_faces_bytes)[0]

        # Verify file size matches expected size for binary STL
        stl_assume_bytes = header_bytes + unsigned_long_int_bytes + number_faces * (
                    vec3_bytes * 3 + spacer_bytes + vec3_bytes)
        if stl_assume_bytes != os.path.getsize(binary_stl_path):
            raise ValueError("STL is not binary or is ill-formatted")

        minx, maxx = [9999999, -9999999]
        miny, maxy = [9999999, -9999999]
        minz, maxz = [9999999, -9999999]

        vertices_length_counter = 0

        data = struct.unpack("<" + "12fH" * number_faces, f.read())
        len_data = len(data)

        for i in range(0, len_data, 13):
            for j in range(3, 12, 3):
                x, y, z = data[i + j:i + j + 3]

                x = int(x * 100000) / 100000
                y = int(y * 100000) / 100000
                z = int(z * 100000) / 100000

                tuple_xyz = (x, y, z)

                try:
                    indices.append(vertices[tuple_xyz])
                except KeyError:
                    vertices[tuple_xyz] = vertices_length_counter
                    vertices_length_counter += 1
                    indices.append(vertices[tuple_xyz])

                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
                if z < minz: minz = z
                if z > maxz: maxz = z

    number_vertices = len(vertices)
    vertices_bytelength = number_vertices * vec3_bytes
    unpadded_indices_bytelength = len(indices) * unsigned_long_int_bytes
    indices_bytelength = (unpadded_indices_bytelength + 3) & ~3

    out_bin_bytelength = vertices_bytelength + indices_bytelength

    # Prepare GLTF JSON
    if is_binary:
        out_bin_uri = ""
    else:
        out_bin_uri = '"uri": "out.bin",'

    gltf2 = '''
{
  "scenes" : [
    {
      "nodes" : [ 0 ]
    }
  ],

  "nodes" : [
    {
      "mesh" : 0
    }
  ],

  "meshes" : [
    {
      "primitives" : [ {
        "attributes" : {
          "POSITION" : 1
        },
        "indices" : 0
      } ]
    }
  ],

  "buffers" : [
    {
      %s
      "byteLength" : %d
    }
  ],
  "bufferViews" : [
    {
      "buffer" : 0,
      "byteOffset" : 0,
      "byteLength" : %d,
      "target" : 34963
    },
    {
      "buffer" : 0,
      "byteOffset" : %d,
      "byteLength" : %d,
      "target" : 34962
    }
  ],
  "accessors" : [
    {
      "bufferView" : 0,
      "byteOffset" : 0,
      "componentType" : 5125,
      "count" : %d,
      "type" : "SCALAR",
      "max" : [ %d ],
      "min" : [ 0 ]
    },
    {
      "bufferView" : 1,
      "byteOffset" : 0,
      "componentType" : 5126,
      "count" : %d,
      "type" : "VEC3",
      "min" : [%f, %f, %f],
      "max" : [%f, %f, %f]
    }
  ],

  "asset" : {
    "version" : "2.0"
  }
}
''' % (
        out_bin_uri,
        out_bin_bytelength,
        indices_bytelength,
        indices_bytelength,
        vertices_bytelength,
        len(indices),
        number_vertices - 1,
        number_vertices,
        minx, miny, minz,
        maxx, maxy, maxz
    )

    # Prepare output binary data
    glb_out = bytearray()
    if is_binary:
        gltf2 = gltf2.replace(" ", "")
        gltf2 = gltf2.replace("\n", "")

        scene = bytearray(gltf2.encode())

        scene_len = len(scene)
        padded_scene_len = (scene_len + 3) & ~3
        body_offset = padded_scene_len + 12 + 8

        file_len = body_offset + out_bin_bytelength + 8

        # 12-byte header
        glb_out.extend(struct.pack('<I', 0x46546C67))  # magic number for glTF
        glb_out.extend(struct.pack('<I', 2))
        glb_out.extend(struct.pack('<I', file_len))

        # chunk 0
        glb_out.extend(struct.pack('<I', padded_scene_len))
        glb_out.extend(struct.pack('<I', 0x4E4F534A))  # magic number for JSON
        glb_out.extend(scene)

        while len(glb_out) < body_offset:
            glb_out.extend(b' ')

        # chunk 1
        glb_out.extend(struct.pack('<I', out_bin_bytelength))
        glb_out.extend(struct.pack('<I', 0x004E4942))  # magic number for BIN

    # Write indices
    glb_out.extend(struct.pack('<%dI' % len(indices), *indices))

    # Padding
    for i in range(indices_bytelength - unpadded_indices_bytelength):
        glb_out.extend(b' ')

    # Prepare vertices data
    reversed_vertices = dict((v, k) for k, v in vertices.items())
    vertices_list = [reversed_vertices[i] for i in range(number_vertices)]
    flattened_vertices = [coord for vertex in vertices_list for coord in vertex]

    # Write vertices
    glb_out.extend(struct.pack('%df' % (number_vertices * 3), *flattened_vertices))

    # Write output files
    with open(out_bin, "wb") as out:
        out.write(glb_out)

    if not is_binary:
        with open(out_gltf, "w") as out:
            out.write(gltf2)

    # Return appropriate paths
    if is_binary:
        return {
            "glb_path": out_bin,
            "is_binary": True
        }
    else:
        return {
            "gltf_path": out_gltf,
            "bin_path": out_bin,
            "is_binary": False
        }


@app.post("/api/convert-stl")
async def convert_stl_to_gltf(
        file: UploadFile = File(...),
        method: str = "trimesh"
):
    """
    Convert STL file to GLTF format using either trimesh or custom implementation.

    Args:
        file: The uploaded STL file
        method: Conversion method - "trimesh" (default) or "custom"

    Returns:
        JSON with download URLs for the converted file(s)
    """
    # Validate file extension
    if not file.filename.lower().endswith('.stl'):
        raise HTTPException(status_code=400, detail="Only STL files are accepted")

    # Create unique filename
    filename = f"{uuid.uuid4()}"
    stl_path = os.path.join(TEMP_DIR, f"{filename}.stl")

    # Save uploaded file
    with open(stl_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        if method.lower() == "trimesh":
            # Use trimesh for conversion (original method)
            gltf_path = os.path.join(TEMP_DIR, f"{filename}.gltf")

            # Load the STL with trimesh
            mesh = trimesh.load(stl_path)

            # Export using trimesh's built-in GLTF exporter
            mesh.export(gltf_path, file_type='gltf')

            # Check if a binary file was created (.bin)
            bin_filename = f"{filename}.bin"
            bin_path = os.path.join(TEMP_DIR, bin_filename)
            bin_url = None

            if os.path.exists(bin_path):
                bin_url = f"/api/files/{bin_filename}"

            return {
                "method": "trimesh",
                "filename": f"{filename}.gltf",
                "download_url": f"/api/files/{filename}.gltf",
                "bin_url": bin_url
            }

        elif method.lower() == "custom":
            # Use custom implementation
            gltf_dir = os.path.join(TEMP_DIR, filename)
            os.makedirs(gltf_dir, exist_ok=True)

            # Convert using custom method (non-binary, split files)
            result = stl_to_gltf_custom(stl_path, gltf_dir, is_binary=False)

            # Move and rename the output files to match our API structure
            gltf_path = os.path.join(TEMP_DIR, f"{filename}.gltf")
            bin_path = os.path.join(TEMP_DIR, f"{filename}.bin")

            shutil.copy(result["gltf_path"], gltf_path)
            shutil.copy(result["bin_path"], bin_path)

            return {
                "method": "custom",
                "filename": f"{filename}.gltf",
                "download_url": f"/api/files/{filename}.gltf",
                "bin_url": f"/api/files/{filename}.bin"
            }

        elif method.lower() == "custom-glb":
            # Use custom implementation with binary output (GLB)
            glb_path = os.path.join(TEMP_DIR, f"{filename}.glb")

            # Convert using custom method (binary, single file)
            result = stl_to_gltf_custom(stl_path, glb_path, is_binary=True)

            return {
                "method": "custom-glb",
                "filename": f"{filename}.glb",
                "download_url": f"/api/files/{filename}.glb"
            }

        else:
            raise HTTPException(status_code=400,
                                detail=f"Invalid method: {method}. Choose 'trimesh', 'custom', or 'custom-glb'")

    except Exception as e:
        # Clean up on error
        if os.path.exists(stl_path):
            os.remove(stl_path)

        # Clean up any other created files
        for ext in ['.gltf', '.glb', '.bin']:
            path = os.path.join(TEMP_DIR, f"{filename}{ext}")
            if os.path.exists(path):
                os.remove(path)

        # Clean up directory if created
        dir_path = os.path.join(TEMP_DIR, filename)
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.get("/api/files/{filename}")
async def get_file(filename: str):
    """
    Serve a converted file.

    Args:
        filename: The filename to download

    Returns:
        The requested file
    """
    file_path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


# New endpoint to get information about available conversion methods
@app.get("/api/conversion-methods")
async def get_conversion_methods():
    """
    Get information about available STL conversion methods.

    Returns:
        JSON with details about available conversion methods
    """
    return {
        "methods": [
            {
                "id": "trimesh",
                "name": "Trimesh",
                "description": "Uses the Trimesh library for conversion. Good for most standard STL files.",
                "output_format": "GLTF + BIN"
            },
            {
                "id": "custom",
                "name": "Custom Implementation",
                "description": "Uses a custom binary conversion algorithm optimized for specific STL formats.",
                "output_format": "GLTF + BIN"
            },
            {
                "id": "custom-glb",
                "name": "Custom GLB Implementation",
                "description": "Uses a custom binary conversion algorithm to produce a single GLB file.",
                "output_format": "GLB (single file)"
            }
        ]
    }

# Run with: uvicorn main:app --reload
