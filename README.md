# StructViz3D API: Advanced 3D Model Conversion Service

## Project Overview

StructViz3D API is a api web service designed for converting STL (STereoLithography) 3D model files into modern, web-friendly 3D file formats including GLTF and GLB. This API provides conversion strategy to ensure maximum compatibility and flexibility for developers working with 3D models.

### 🚀 Implemented Demo and Live API

https://yadnyeshkolte.github.io/structviz3d-react/

## Technologies Used

- **Backend Framework**: FastAPI
- **Programming Language**: Python 3.8+
- **3D Model Processing**: 
  - Trimesh
  - Custom binary manipulation
- **Deployment**: Render.com
- **CORS Support**: FastAPI CORS Middleware
- **File Handling**: 
  - Python's `os` and `shutil`
  - Temporary file management

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip package manager
- Virtual environment (recommended)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/structviz3d-api.git
cd structviz3d-api
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Local Development

Start the development server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Convert STL Endpoint
`POST /api/convert-stl`

#### Parameters
- `file`: STL file to convert (multipart/form-data)
- `method`: Conversion method (optional, default: "trimesh")

#### Supported Methods
- `trimesh`: Default Trimesh library conversion
- `custom`: Custom binary conversion (GLTF + BIN)
- `custom-glb`: Custom binary conversion (Single GLB file)

### File Download Endpoint
`GET /api/files/{filename}`

Retrieves converted 3D model files.

### Conversion Methods Endpoint
`GET /api/conversion-methods`

Returns detailed information about available conversion strategies.

## Conversion Methods

### Trimesh Conversion
- Uses Trimesh library's built-in GLTF exporter
- Suitable for most standard STL files
- Produces GLTF with separate BIN file
- Fastest and most straightforward method

### Custom Conversion
- Implements a custom binary manipulation algorithm
- More control over conversion process
- Produces GLTF with separate BIN file
- Optimized for specific STL formats

### Custom GLB Conversion
- Creates a single, compact GLB file
- Ideal for web and mobile 3D rendering
- Reduces file transfer overhead
- Maintains high-quality geometry

## Usage Examples

### Python Requests
```python
import requests

url = "https://your-render-url.com/api/convert-stl"
with open("model.stl", "rb") as file:
    files = {"file": file}
    params = {"method": "custom-glb"}
    response = requests.post(url, files=files, params=params)
    
if response.status_code == 200:
    download_url = response.json()["download_url"]
    print(f"Converted file available at: {download_url}")
```

### JavaScript Fetch
```javascript
const convertSTL = async (file, method = "trimesh") => {
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch("/api/convert-stl", {
            method: "POST",
            body: formData
        });
        const result = await response.json();
        return result.download_url;
    } catch (error) {
        console.error("Conversion failed:", error);
    }
};
```

### Curl Command
```bash
curl -X POST \
  -F "file=@/path/to/model.stl" \
  -F "method=custom-glb" \
  https://your-render-url.com/api/convert-stl
```

## Configuration

Key configuration options:
- `TEMP_DIR`: Temporary file storage location
- CORS settings in `main.py`
- Conversion method defaults

## Error Handling

The API provides comprehensive error responses:
- 400 Bad Request: Invalid file type or conversion method
- 500 Internal Server Error: Conversion process failure

## Performance Considerations

- Temporary files are automatically cleaned up
- Support for multiple concurrent conversions
- Efficient memory management
- Configurable conversion methods

## Security

- File type validation
- Unique filename generation
- Temporary storage with automatic cleanup
- CORS configuration for controlled access

## Deployment

### Render.com Deployment Steps
1. Create a new Web Service
2. Connect your GitHub repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Environment Variables
- Set `PORT` for Render.com compatibility
- Configure any additional settings

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---
