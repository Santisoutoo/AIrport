import hashlib
import os
from typing import Optional, Tuple

import psycopg2
from psycopg2 import sql


class UserService:
    """Servicio para gestionar usuarios en PostgreSQL."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "airport",
        user: str = "airport_user",
        password: str = "airport_dev_pass",
    ):
        self.connection_params = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }
        self._connection = None

    def _get_connection(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.connection_params)
        return self._connection

    def _close_connection(self):
        """Cierra la conexion a la base de datos."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None

    @staticmethod
    def _hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        """
        Genera un hash seguro de la contrasena.
        Retorna el hash y el salt usado.
        """
        if salt is None:
            salt = os.urandom(32)

        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            100000  # iteraciones
        )
        # Guardamos salt + hash juntos
        combined = salt + pwd_hash
        return combined.hex(), salt

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        """Verifica si la contrasena coincide con el hash almacenado."""
        try:
            combined = bytes.fromhex(stored_hash)
            salt = combined[:32]
            stored_pwd_hash = combined[32:]

            pwd_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                100000
            )
            return pwd_hash == stored_pwd_hash
        except (ValueError, IndexError):
            return False

    def create_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Crea un nuevo usuario.
        Retorna (success, message).
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Verificar si el usuario ya existe
            cursor.execute(
                "SELECT id FROM users WHERE username = %s",
                (username,)
            )
            if cursor.fetchone():
                return False, "Username already exists"

            password_hash, _ = self._hash_password(password)

            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, password_hash)
            )
            conn.commit()
            cursor.close()

            return True, "User created successfully"

        except psycopg2.Error as e:
            if self._connection:
                self._connection.rollback()
            return False, f"Database error: {str(e)}"

    def verify_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Verifica las credenciales de un usuario (login).
        Retorna (success, message).
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT password_hash FROM users WHERE username = %s",
                (username,)
            )
            result = cursor.fetchone()
            cursor.close()

            if not result:
                return False, "Invalid username or password"

            stored_hash = result[0]
            if self._verify_password(password, stored_hash):
                return True, "Login successful"
            else:
                return False, "Invalid username or password"

        except psycopg2.Error as e:
            return False, f"Database error: {str(e)}"

    def user_exists(self, username: str) -> bool:
        """Verifica si un usuario existe."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT 1 FROM users WHERE username = %s",
                (username,)
            )
            result = cursor.fetchone()
            cursor.close()

            return result is not None

        except psycopg2.Error:
            return False

    def __del__(self):
        """Destructor para cerrar la conexion."""
        self._close_connection()
