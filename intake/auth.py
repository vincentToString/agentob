import jwt
import time
import aiohttp
from datetime import datetime, timedelta

class GitHubAppAuth:
    def __init__(self, app_id: str, private_key_path: str, installation_id: str) -> None:
        self.app_id = app_id
        self.private_key_path = private_key_path
        self.installation_id = installation_id

        with open(private_key_path, 'r') as f:
            self.private_key = f.read()

        self._token = None
        self._token_expires_at = None
    
    def _generate_jwt(self) -> str:
        """Generate JWT to authenticate as the GitHub APP"""
        payload = {
            'iat': int(time.time()),
            'exp': int(time.time()) + 600,  # JWT expires in 10 minutes
            'iss': self.app_id
        }
        return jwt.encode(payload, self.private_key, algorithm='RS256')
    
    async def get_installation_token(self) -> str:
        """Get installation access token (cached)"""
        # Return cached token if still valid
        if self._token and self._token_expires_at and datetime.now() < self._token_expires_at:
            return self._token
        
        # Generate new token
        jwt_token = self._generate_jwt()
        
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'PR-Owl-Bot'
        }
        
        url = f'https://api.github.com/app/installations/{self.installation_id}/access_tokens'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                
                self._token = data['token']
                # Tokens expire in 1 hour, refresh 5 min early
                self._token_expires_at = datetime.now() + timedelta(minutes=55)
                
                return self._token
    