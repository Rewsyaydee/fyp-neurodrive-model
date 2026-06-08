from flask import send_from_directory
import os
from pathlib import Path

def register_static_routes(app):
    """Register static file serving routes"""

    @app.route('/data/<filename>')
    def serve_data(filename):
        """Serve CSV data files from data directory"""
        data_dir = Path(__file__).parent / "data"
        return send_from_directory(data_dir, filename, as_attachment=True)

    @app.route('/artifacts/<path:filename>')
    def serve_artifacts(filename):
        """Serve files from artifacts directory"""
        artifacts_dir = Path(__file__).parent / "artifacts"
        return send_from_directory(artifacts_dir, filename)