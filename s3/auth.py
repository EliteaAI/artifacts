# pylint: disable=C0116
#
#   Copyright 2026 EPAM Systems
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

""" AWS Signature Version 4 Authentication for S3-compatible API """

import hmac
import hashlib
from functools import wraps
from typing import Optional, Tuple, NamedTuple
from urllib.parse import quote

import flask
from flask import request, g
from pylon.core.tools import log

from tools import context, auth


class S3Credentials(NamedTuple):
    """Parsed S3 credentials from request"""
    access_key_id: str
    secret_access_key: str
    project_id: int
    user_id: int
    name: str


class S3AuthContext(NamedTuple):
    """Authentication context for S3 request"""
    credentials: S3Credentials
    project: dict
    region: str
    service: str


class SigV4Components(NamedTuple):
    """Parsed AWS Signature V4 components"""
    access_key: str
    date: str
    region: str
    service: str
    signed_headers: list
    signature: str


def sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256 signing helper"""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    """
    Derive the signing key for AWS Signature Version 4.

    The signing key is derived from the secret access key through a series of
    HMAC-SHA256 operations: kSecret -> kDate -> kRegion -> kService -> kSigning
    """
    k_date = sign(('AWS4' + secret_key).encode('utf-8'), date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, service)
    k_signing = sign(k_service, 'aws4_request')
    return k_signing


def hash_payload(payload: bytes) -> str:
    """Calculate SHA256 hash of the payload"""
    return hashlib.sha256(payload).hexdigest()


def parse_authorization_header(auth_header: str) -> Optional[SigV4Components]:
    """
    Parse AWS Signature V4 Authorization header.

    Format: AWS4-HMAC-SHA256 Credential=ACCESS_KEY/DATE/REGION/SERVICE/aws4_request,
            SignedHeaders=host;x-amz-content-sha256;x-amz-date,
            Signature=SIGNATURE
    """
    if not auth_header or not auth_header.startswith('AWS4-HMAC-SHA256'):
        return None

    try:
        # Remove the algorithm prefix
        parts = auth_header[len('AWS4-HMAC-SHA256 '):].strip()

        # Parse key=value pairs
        components = {}
        for part in parts.split(','):
            part = part.strip()
            if '=' in part:
                key, value = part.split('=', 1)
                components[key.strip()] = value.strip()

        # Parse Credential
        credential = components.get('Credential', '')
        cred_parts = credential.split('/')
        if len(cred_parts) != 5:
            log.warning("Invalid credential format: %s", credential)
            return None

        access_key, date, region, service, _ = cred_parts

        # Parse SignedHeaders
        signed_headers = components.get('SignedHeaders', '').split(';')

        # Get Signature
        signature = components.get('Signature', '')

        return SigV4Components(
            access_key=access_key,
            date=date,
            region=region,
            service=service,
            signed_headers=signed_headers,
            signature=signature
        )
    except Exception as e:
        log.warning("Failed to parse Authorization header: %s", e)
        return None


def parse_query_string_auth() -> Optional[SigV4Components]:
    """
    Parse AWS Signature V4 from query string (presigned URLs).

    Query params: X-Amz-Algorithm, X-Amz-Credential, X-Amz-Date,
                  X-Amz-SignedHeaders, X-Amz-Signature
    """
    algorithm = request.args.get('X-Amz-Algorithm')
    if algorithm != 'AWS4-HMAC-SHA256':
        return None

    try:
        credential = request.args.get('X-Amz-Credential', '')
        cred_parts = credential.split('/')
        if len(cred_parts) != 5:
            return None

        access_key, date, region, service, _ = cred_parts
        signed_headers = request.args.get('X-Amz-SignedHeaders', '').split(';')
        signature = request.args.get('X-Amz-Signature', '')

        return SigV4Components(
            access_key=access_key,
            date=date,
            region=region,
            service=service,
            signed_headers=signed_headers,
            signature=signature
        )
    except Exception as e:
        log.warning("Failed to parse query string auth: %s", e)
        return None


def get_canonical_uri(path: str) -> str:
    """Get canonical URI (URL-encoded path)"""
    # S3 uses single URL encoding for the path
    return quote(path, safe='/')


def get_canonical_query_string() -> str:
    """
    Get canonical query string.

    - Sort query params by key name
    - URL-encode keys and values
    - Exclude X-Amz-Signature from the canonical query string
    """
    params = []
    for key in sorted(request.args.keys()):
        if key == 'X-Amz-Signature':
            continue
        value = request.args.get(key, '')
        params.append(f"{quote(key, safe='')}={quote(value, safe='')}")
    return '&'.join(params)


def get_canonical_headers(signed_headers: list) -> str:
    """
    Get canonical headers.

    - Lowercase header names
    - Trim whitespace from values
    - Sort by header name
    """
    headers = []
    for header_name in sorted(signed_headers):
        header_name_lower = header_name.lower()
        if header_name_lower == 'host':
            value = request.host
        else:
            value = request.headers.get(header_name, '')
        # Trim and collapse whitespace
        value = ' '.join(value.split())
        headers.append(f"{header_name_lower}:{value}")
    return '\n'.join(headers) + '\n'


def get_payload_hash() -> str:
    """
    Get the hash of the request payload.

    For S3, this can be:
    - The actual SHA256 of the body
    - 'UNSIGNED-PAYLOAD' for unsigned payloads
    - Value from x-amz-content-sha256 header
    """
    # Check if client provided the hash
    content_sha256 = request.headers.get('x-amz-content-sha256', '')

    if content_sha256 == 'UNSIGNED-PAYLOAD':
        return 'UNSIGNED-PAYLOAD'

    if content_sha256 == 'STREAMING-AWS4-HMAC-SHA256-PAYLOAD':
        # Chunked upload - for now, just accept it
        return content_sha256

    if content_sha256:
        return content_sha256

    # Calculate hash from body
    return hash_payload(request.get_data())


def create_canonical_request(signed_headers: list) -> str:
    """
    Create the canonical request string.

    Format:
    HTTPMethod\n
    CanonicalURI\n
    CanonicalQueryString\n
    CanonicalHeaders\n
    SignedHeaders\n
    HashedPayload
    """
    method = request.method
    canonical_uri = get_canonical_uri(request.path)
    canonical_query = get_canonical_query_string()
    canonical_headers = get_canonical_headers(signed_headers)
    signed_headers_str = ';'.join(sorted(h.lower() for h in signed_headers))
    payload_hash = get_payload_hash()

    canonical_request = '\n'.join([
        method,
        canonical_uri,
        canonical_query,
        canonical_headers,
        signed_headers_str,
        payload_hash
    ])

    return canonical_request


def create_string_to_sign(canonical_request: str, amz_date: str,
                          date_stamp: str, region: str, service: str) -> str:
    """
    Create the string to sign.

    Format:
    Algorithm\n
    RequestDateTime\n
    CredentialScope\n
    HashedCanonicalRequest
    """
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    hashed_canonical = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()

    return '\n'.join([
        algorithm,
        amz_date,
        credential_scope,
        hashed_canonical
    ])


def calculate_signature(string_to_sign: str, secret_key: str,
                       date_stamp: str, region: str, service: str) -> str:
    """Calculate the AWS Signature V4 signature"""
    signing_key = get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature


def lookup_credentials(access_key_id: str) -> Optional[S3Credentials]:
    """
    Look up S3 credentials by access key ID.

    Returns the credentials if found, None otherwise.
    """
    try:
        rpc = context.rpc_manager
        # Look up in configurations where type='s3_credentials'
        credentials = rpc.timeout(5).s3_credentials_get_by_access_key(
            access_key_id=access_key_id
        )
        if credentials:
            return S3Credentials(
                access_key_id=credentials['access_key_id'],
                secret_access_key=credentials['secret_access_key'],
                project_id=credentials['project_id'],
                user_id=credentials['user_id'],
                name=credentials.get('name', '')
            )
    except Exception as e:
        log.warning("Failed to lookup credentials for %s: %s", access_key_id, e)
    return None


def verify_signature(sig_components: SigV4Components,
                     credentials: S3Credentials) -> bool:
    """
    Verify the AWS Signature V4 signature.

    Returns True if the signature is valid, False otherwise.
    """
    try:
        # Get the x-amz-date header or query param
        amz_date = request.headers.get('x-amz-date') or request.args.get('X-Amz-Date', '')
        if not amz_date:
            log.warning("Missing x-amz-date")
            return False

        # Extract date stamp (YYYYMMDD) from amz_date (YYYYMMDDTHHMMSSZ)
        date_stamp = amz_date[:8]

        # Verify date matches credential scope
        if date_stamp != sig_components.date:
            log.warning("Date mismatch: %s vs %s", date_stamp, sig_components.date)
            return False

        # Create canonical request
        canonical_request = create_canonical_request(sig_components.signed_headers)

        # Create string to sign
        string_to_sign = create_string_to_sign(
            canonical_request, amz_date, date_stamp,
            sig_components.region, sig_components.service
        )

        # Calculate expected signature
        expected_signature = calculate_signature(
            string_to_sign, credentials.secret_access_key,
            date_stamp, sig_components.region, sig_components.service
        )

        # Compare signatures (constant time comparison)
        return hmac.compare_digest(expected_signature, sig_components.signature)

    except Exception as e:
        log.warning("Signature verification failed: %s", e)
        return False


def authenticate_bearer_request() -> Tuple[Optional[S3AuthContext], Optional[str]]:
    """
    Authenticate an S3 request using Bearer token.

    Returns:
        Tuple of (S3AuthContext, None) on success
        Tuple of (None, error_message) on failure
    """
    try:
        # Get project_id from query parameter (required for Bearer auth)
        project_id_str = request.args.get('project_id')
        if not project_id_str:
            return None, "project_id query parameter required for Bearer token auth"

        try:
            project_id = int(project_id_str)
        except ValueError:
            return None, "Invalid project_id query parameter value"

        # Use flask.g.auth which is populated by the auth middleware
        if not hasattr(flask.g, 'auth'):
            return None, "Authentication context not available"

        auth_data = flask.g.auth
        if auth_data.type == 'public' or auth_data.id == '-':
            return None, "Not authenticated"

        # Get user info from auth context
        user = auth.current_user()
        if not user or not user.get('id'):
            return None, "Could not determine user from token"

        user_id = user['id']
        user_name = user.get('name', user.get('email', 'Bearer User'))

        # Verify user has access to the project
        rpc = context.rpc_manager
        try:
            has_access = rpc.timeout(5).auth_check_user_in_project(
                user_id=user_id,
                project_id=project_id
            )
            if not has_access:
                return None, "User does not have access to this project"
        except Exception as e:
            log.warning("Failed to check project access: %s", e)

        # Get project
        try:
            project = rpc.call.project_get_by_id(project_id=project_id)
            if not project:
                return None, "Project not found"
        except Exception as e:
            log.warning("Failed to get project: %s", e)
            return None, "Project lookup failed"

        # Get or create S3 credentials for this project
        try:
            cred_data = rpc.timeout(5).s3_credentials_get_or_create_for_bearer(
                project_id=project_id,
                user_id=user_id,
                user_name=user_name
            )
            if not cred_data:
                return None, "Failed to get S3 credentials for project"
        except Exception as e:
            log.error("Failed to get/create S3 credentials: %s", e)
            return None, "Failed to get S3 credentials"

        # Build credentials object
        credentials = S3Credentials(
            access_key_id=cred_data.get('access_key_id', 'bearer-auth'),
            secret_access_key=cred_data.get('secret_access_key', ''),
            project_id=project_id,
            user_id=user_id,
            name=cred_data.get('name', user_name)
        )

        return S3AuthContext(
            credentials=credentials,
            project=project,
            region='us-east-1',  # Default region for Bearer auth
            service='s3'
        ), None

    except Exception as e:
        log.error("Bearer auth failed: %s", e)
        return None, f"Bearer authentication failed: {str(e)}"


def authenticate_s3_request() -> Tuple[Optional[S3AuthContext], Optional[str]]:
    """
    Authenticate an S3 request.
    Supports both AWS Signature V4 and Bearer token authentication.

    Returns:
        Tuple of (S3AuthContext, None) on success
        Tuple of (None, error_message) on failure
    """
    auth_header = request.headers.get('Authorization', '')

    # Check for Bearer token first
    if auth_header.startswith('Bearer '):
        return authenticate_bearer_request()

    # Try AWS SigV4 header-based auth
    sig_components = parse_authorization_header(auth_header)

    # Try query string auth if no header
    if not sig_components:
        sig_components = parse_query_string_auth()

    if not sig_components:
        return None, "Missing or invalid authentication"

    # Look up credentials
    credentials = lookup_credentials(sig_components.access_key)
    if not credentials:
        return None, "Invalid access key"

    # Verify signature
    if not verify_signature(sig_components, credentials):
        return None, "Invalid signature"

    # Get project
    try:
        rpc = context.rpc_manager
        project = rpc.call.project_get_by_id(project_id=credentials.project_id)
        if not project:
            return None, "Project not found"
    except Exception as e:
        log.warning("Failed to get project: %s", e)
        return None, "Project lookup failed"

    return S3AuthContext(
        credentials=credentials,
        project=project,
        region=sig_components.region,
        service=sig_components.service
    ), None


def s3_auth_required(f):
    """
    Decorator to require S3 authentication for a route.

    Sets g.s3_auth with the authentication context on success.
    Returns S3 error response on failure.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from .responses import error_response

        auth_context, error = authenticate_s3_request()

        if error:
            log.warning("S3 auth failed: %s", error)
            return error_response(
                code='AccessDenied',
                message=error,
                status_code=403
            )

        # Store auth context in Flask's g object
        g.s3_auth = auth_context

        return f(*args, **kwargs)

    return decorated_function


def verify_bearer_auth(flask_request) -> dict:
    """
    Verify Bearer token authentication for S3 requests.

    Uses the platform's standard Bearer token authentication.
    Requires project_id query parameter to identify the project.

    Args:
        flask_request: The Flask request object

    Returns:
        dict with either:
            {'credential': credential_dict} on success
            {'error': error_message} on failure
    """
    try:
        project_id_str = flask_request.args.get('project_id')
        if not project_id_str:
            return {'error': 'project_id query parameter required for Bearer token auth'}

        try:
            project_id = int(project_id_str)
        except ValueError:
            return {'error': 'Invalid project_id query parameter value'}

        if not hasattr(flask.g, 'auth'):
            return {'error': 'Authentication context not available'}

        auth_data = flask.g.auth
        if auth_data.type == 'public' or auth_data.id == '-':
            return {'error': 'Not authenticated'}

        user = auth.current_user()
        if not user or not user.get('id'):
            return {'error': 'Could not determine user from token'}

        user_id = user['id']

        rpc = context.rpc_manager
        try:
            has_access = rpc.timeout(5).auth_check_user_in_project(
                user_id=user_id,
                project_id=project_id
            )
            if not has_access:
                return {'error': 'User does not have access to this project'}
        except Exception as e:
            log.warning("Failed to check project access: %s", e)

        try:
            credentials = rpc.timeout(5).s3_credentials_get_or_create_for_bearer(
                project_id=project_id,
                user_id=user_id,
                user_name=user.get('name', user.get('email', 'Bearer User'))
            )
            if not credentials:
                return {'error': 'Failed to get S3 credentials for project'}
        except Exception as e:
            log.error("Failed to get/create S3 credentials: %s", e)
            return {'error': 'Failed to get S3 credentials'}

        return {
            'credential': {
                'access_key_id': credentials.get('access_key_id', 'bearer-auth'),
                'project_id': project_id,
                'user_id': user_id,
                'name': credentials.get('name', 'Bearer Token User'),
                'bucket_permissions': credentials.get('bucket_permissions', {}),
            }
        }

    except Exception as e:
        log.error("Bearer auth verification failed: %s", e)
        return {'error': f'Bearer authentication failed: {str(e)}'}


def verify_s3_auth(flask_request) -> dict:
    """
    Verify S3 authentication for a request.

    This is a non-decorator version for use in route handlers.
    Supports AWS Signature V4, Bearer token, and session authentication.

    Priority:
    1. AWS SigV4 (Authorization header or query string)
    2. Bearer token (Authorization: Bearer ...)
    3. Session auth (no Authorization header - uses auth.current_user())

    Args:
        flask_request: The Flask request object

    Returns:
        dict with either:
            {'credential': credential_dict} on success
            {'error': error_message} on failure
    """
    auth_header = flask_request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer ') or not auth_header:
        return verify_bearer_auth(flask_request)

    # Try AWS SigV4 header-based auth
    sig_components = parse_authorization_header(auth_header)

    # Try query string auth if no header
    if not sig_components:
        sig_components = parse_query_string_auth()

    if not sig_components:
        return {'error': 'Missing or invalid authentication'}

    # Look up credentials
    credentials = lookup_credentials(sig_components.access_key)
    if not credentials:
        return {'error': 'Invalid access key'}

    # Verify signature
    if not verify_signature(sig_components, credentials):
        return {'error': 'Invalid signature'}

    # Look up full credential data to get bucket_permissions
    rpc = context.rpc_manager
    full_cred = rpc.timeout(5).s3_credentials_get_by_access_key(
        access_key_id=credentials.access_key_id
    )
    bucket_permissions = full_cred.get('bucket_permissions', {}) if full_cred else {}

    # Return credential info
    return {
        'credential': {
            'access_key_id': credentials.access_key_id,
            'project_id': credentials.project_id,
            'user_id': credentials.user_id,
            'name': credentials.name,
            'bucket_permissions': bucket_permissions,
        }
    }
