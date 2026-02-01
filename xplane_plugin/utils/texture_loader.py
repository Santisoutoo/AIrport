from PIL import Image
import OpenGL.GL as gl
from pathlib import Path


class TextureLoader:
    """Carga y gestiona texturas para imgui."""

    _textures = {}

    @classmethod
    def load(cls, image_path: str) -> tuple:
        """
        Carga una imagen como textura OpenGL.
        Retorna (texture_id, width, height) o (None, 0, 0) si falla.
        """
        if image_path in cls._textures:
            return cls._textures[image_path]

        try:
            path = Path(image_path)
            if not path.exists():
                return None, 0, 0

            img = Image.open(path).convert('RGBA')
            img_data = img.tobytes()

            texture_id = gl.glGenTextures(1)
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexImage2D(
                gl.GL_TEXTURE_2D, 0, gl.GL_RGBA,
                img.width, img.height, 0,
                gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, img_data
            )

            cls._textures[image_path] = (texture_id, img.width, img.height)
            return texture_id, img.width, img.height

        except Exception:
            return None, 0, 0

    @classmethod
    def unload_all(cls):
        """Libera todas las texturas."""
        for texture_id, _, _ in cls._textures.values():
            if texture_id:
                gl.glDeleteTextures(1, [texture_id])
        cls._textures.clear()
