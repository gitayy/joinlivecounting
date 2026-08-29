from .config import PORT
from .web.app import app

app.run(port=PORT, debug=True)
