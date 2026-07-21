"""
Dhan Token Manager Module
Handles Dhan access token status checking and (re)generation.

Dhan's retail access token is valid for ~24 hours and is not renewed via an
OAuth code-exchange the way Upstox's was. Two generation paths are supported:
  1. TOTP-based auto-generation (DhanLogin.generate_token(pin, totp)) - requires
     DHAN_PIN + DHAN_TOTP_SECRET to be configured, enabling unattended daily
     refresh (e.g. via a cron-style scheduled job before market open).
  2. Manual paste - the user copies a token from the Dhan web portal
     (web.dhan.co -> My Profile -> DhanHQ Trading APIs -> Generate Token).
"""

import os
from datetime import datetime
from dotenv import load_dotenv, set_key

from dhanhq import DhanLogin

import config
import logger

try:
    import pyotp
except ImportError:
    pyotp = None


class DhanTokenManager:
    """Manages Dhan access token operations"""

    DHAN_LOGIN_PORTAL_URL = "https://web.dhan.co/login"

    def __init__(self):
        self.env_file = os.path.join(config.PROJECT_ROOT, ".env")
        self.timestamp_file = os.path.join(config.BASE_DIR, ".dhan_token_timestamp")
        load_dotenv(self.env_file)

    def validate_token_with_api(self):
        """
        Perform a lightweight API call (user profile) to verify the token is valid.
        """
        token = os.getenv("DHAN_ACCESS_TOKEN")
        client_id = os.getenv("DHAN_CLIENT_ID")
        if not token or not client_id:
            return False, "Token or Client ID missing"

        try:
            login = DhanLogin(client_id)
            profile = login.user_profile(token)

            if profile and profile.get('dhanClientId'):
                return True, "Token is active"

            return False, f"Token validation failed: {profile}"

        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def get_token_status(self):
        """
        Check if the current Dhan access token is valid and when it was generated

        Returns:
            Dict with is_valid, generated_at, age_hours, status, message
        """
        try:
            token = os.getenv("DHAN_ACCESS_TOKEN")
            if not token:
                return {
                    "is_valid": False,
                    "generated_at": None,
                    "age_hours": None,
                    "status": "missing",
                    "message": "Token not found. Please generate a new token."
                }

            generated_at_dt = None
            if os.path.exists(self.timestamp_file):
                try:
                    with open(self.timestamp_file, 'r') as f:
                        generated_at_dt = datetime.fromisoformat(f.read().strip())
                except Exception:
                    pass

            if not generated_at_dt and os.path.exists(self.env_file):
                generated_at_dt = datetime.fromtimestamp(os.path.getmtime(self.env_file))

            is_api_valid, api_message = self.validate_token_with_api()

            if generated_at_dt:
                age_hours = (datetime.now() - generated_at_dt).total_seconds() / 3600
                return {
                    "is_valid": is_api_valid,
                    "generated_at": generated_at_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "age_hours": round(age_hours, 1),
                    "status": "valid" if is_api_valid else "expired",
                    "message": api_message
                }

            return {
                "is_valid": is_api_valid,
                "generated_at": "Unknown",
                "age_hours": 0,
                "status": "valid" if is_api_valid else "expired",
                "message": api_message
            }

        except Exception as e:
            logger.error(f"Error checking Dhan token status: {str(e)}")
            return {
                "is_valid": False,
                "generated_at": None,
                "age_hours": None,
                "status": "error",
                "message": f"Error: {str(e)}"
            }

    def get_login_url(self):
        """
        Return the Dhan web portal URL where the user manually generates an
        access token (there is no OAuth authorize-redirect for this app type).
        """
        return self.DHAN_LOGIN_PORTAL_URL

    def generate_access_token_via_totp(self):
        """
        Automated token generation using PIN + TOTP (no browser interaction).
        Requires DHAN_CLIENT_ID, DHAN_PIN, and DHAN_TOTP_SECRET to be configured.

        Returns:
            Dict with success status and message
        """
        try:
            if pyotp is None:
                return {"success": False, "message": "pyotp package not installed (pip install pyotp)"}

            client_id = config.DHAN_CLIENT_ID
            pin = config.DHAN_PIN
            totp_secret = config.DHAN_TOTP_SECRET

            if not client_id or not pin or not totp_secret:
                return {
                    "success": False,
                    "message": "DHAN_CLIENT_ID / DHAN_PIN / DHAN_TOTP_SECRET not configured in .env"
                }

            totp_code = pyotp.TOTP(totp_secret).now()

            login = DhanLogin(client_id)
            result = login.generate_token(pin, totp_code)

            access_token = result.get('accessToken') or result.get('access_token')
            if not access_token:
                logger.error(f"TOTP token generation failed: {result}")
                return {"success": False, "message": f"Dhan API Error: {result}"}

            return self.save_manual_token(access_token)

        except Exception as e:
            logger.error(f"Error generating Dhan token via TOTP: {str(e)}")
            return {"success": False, "message": f"Server Error: {str(e)}"}

    def save_manual_token(self, access_token):
        """
        Save a Dhan access token (manually pasted or TOTP-generated) to .env

        Args:
            access_token: The access token string

        Returns:
            Dict with success status and message
        """
        try:
            if not access_token or len(access_token) < 10:
                return {"success": False, "message": "Invalid access token format"}

            if os.path.exists(self.env_file):
                set_key(self.env_file, 'DHAN_ACCESS_TOKEN', access_token)
            else:
                with open(self.env_file, 'w') as f:
                    f.write(f"DHAN_ACCESS_TOKEN={access_token}\n")

            os.environ['DHAN_ACCESS_TOKEN'] = access_token
            config.DHAN_ACCESS_TOKEN = access_token

            with open(self.timestamp_file, 'w') as f:
                f.write(datetime.now().isoformat())

            logger.info("✅ Dhan access token saved successfully")

            return {
                "success": True,
                "message": "Token saved successfully!",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            logger.error(f"Error saving Dhan token: {str(e)}")
            return {"success": False, "message": f"Server Error: {str(e)}"}


# Global instance
dhan_token_manager = DhanTokenManager()
