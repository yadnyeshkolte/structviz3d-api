from mangum import Mangum
from main import app
import os

# Remove local file storage
os.environ['STORAGE_TYPE'] = 'cloudflare'

# Create Mangum handler
handler = Mangum(app)