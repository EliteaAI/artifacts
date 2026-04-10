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

""" S3 XML/JSON Response Builders """

import json
from datetime import datetime
from typing import List, Dict, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from flask import Response, request


S3_NAMESPACE = 'http://s3.amazonaws.com/doc/2006-03-01/'


def _create_root(tag: str) -> Element:
    """Create root element with S3 namespace"""
    return Element(tag, xmlns=S3_NAMESPACE)


def _format_datetime(dt: datetime) -> str:
    """Format datetime in S3 format (RFC-3339 / ISO 8601 with Z suffix)"""
    if isinstance(dt, str):
        # Ensure string dates have proper format with Z suffix
        # Input might be ISO format from filesystem: '2025-12-19T19:35:59.123456'
        # AWS SDK requires RFC-3339 format: '2025-12-19T19:35:59.000Z'
        if 'Z' not in dt and '+' not in dt:
            # Strip microseconds if present and add Z suffix
            if '.' in dt:
                dt = dt.split('.')[0] + '.000Z'
            else:
                dt = dt + '.000Z'
        return dt
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')


def _get_output_format() -> str:
    """Get the requested output format from query parameter (xml or json)"""
    return request.args.get('format', 'xml').lower()


def _to_xml_response(root: Element, status_code: int = 200) -> Response:
    """Convert Element to Flask Response with proper headers"""
    xml_str = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding='utf-8')
    return Response(
        xml_str,
        status=status_code,
        mimetype='application/xml'
    )


def _to_json_response(data: Dict, status_code: int = 200) -> Response:
    """Convert dict to Flask JSON Response"""
    return Response(
        json.dumps(data, indent=2),
        status=status_code,
        mimetype='application/json'
    )


def error_response(code: str, message: str, resource: str = '',
                   request_id: str = '', status_code: int = 400) -> Response:
    """
    Generate S3 error response in XML or JSON format.

    XML Example:
    <Error>
        <Code>NoSuchBucket</Code>
        <Message>The specified bucket does not exist</Message>
        <Resource>/mybucket</Resource>
        <RequestId>4442587FB7D0A2F9</RequestId>
    </Error>

    JSON Example:
    {
        "error": {
            "code": "NoSuchBucket",
            "message": "The specified bucket does not exist",
            "resource": "/mybucket",
            "requestId": "4442587FB7D0A2F9"
        }
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'error': {
                'code': code,
                'message': message
            }
        }
        if resource:
            data['error']['resource'] = resource
        if request_id:
            data['error']['requestId'] = request_id
        return _to_json_response(data, status_code)

    # Default to XML
    root = Element('Error')
    SubElement(root, 'Code').text = code
    SubElement(root, 'Message').text = message
    if resource:
        SubElement(root, 'Resource').text = resource
    if request_id:
        SubElement(root, 'RequestId').text = request_id

    return _to_xml_response(root, status_code)


def list_buckets_response(buckets: List[Dict], owner_id: str = '',
                          owner_display_name: str = '') -> Response:
    """
    Generate ListBuckets response in XML or JSON format.

    XML Example:
    <ListAllMyBucketsResult>
        <Owner>
            <ID>owner-id</ID>
            <DisplayName>owner-name</DisplayName>
        </Owner>
        <Buckets>
            <Bucket>
                <Name>mybucket</Name>
                <CreationDate>2024-01-01T00:00:00.000Z</CreationDate>
                <Size>1024000</Size>
                <RetentionDays>30</RetentionDays>
            </Bucket>
        </Buckets>
    </ListAllMyBucketsResult>

    JSON Example:
    {
        "owner": {
            "id": "owner-id",
            "displayName": "owner-name"
        },
        "buckets": [
            {
                "name": "mybucket",
                "creationDate": "2024-01-01T00:00:00.000Z",
                "size": 1024000,
                "retentionDays": 30
            }
        ]
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'owner': {
                'id': owner_id,
                'displayName': owner_display_name
            },
            'buckets': []
        }
        for bucket in buckets:
            creation_date = bucket.get('creation_date', datetime.utcnow())
            bucket_data = {
                'name': bucket['name'],
                'creationDate': _format_datetime(creation_date),
                'size': bucket.get('size', 0)
            }
            retention_days = bucket.get('retention_days')
            if retention_days is not None:
                bucket_data['retentionDays'] = retention_days
            data['buckets'].append(bucket_data)
        return _to_json_response(data)

    # Default to XML
    root = _create_root('ListAllMyBucketsResult')

    owner = SubElement(root, 'Owner')
    SubElement(owner, 'ID').text = owner_id
    SubElement(owner, 'DisplayName').text = owner_display_name

    buckets_elem = SubElement(root, 'Buckets')
    for bucket in buckets:
        bucket_elem = SubElement(buckets_elem, 'Bucket')
        SubElement(bucket_elem, 'Name').text = bucket['name']
        creation_date = bucket.get('creation_date', datetime.utcnow())
        SubElement(bucket_elem, 'CreationDate').text = _format_datetime(creation_date)
        SubElement(bucket_elem, 'Size').text = str(bucket.get('size', 0))
        retention_days = bucket.get('retention_days')
        if retention_days is not None:
            SubElement(bucket_elem, 'RetentionDays').text = str(retention_days)

    return _to_xml_response(root)


def list_objects_v2_response(bucket: str, objects: List[Dict],
                             prefix: str = '', delimiter: str = '',
                             max_keys: int = 1000,
                             continuation_token: str = '',
                             next_continuation_token: str = '',
                             is_truncated: bool = False,
                             common_prefixes: List[str] = None) -> Response:
    """
    Generate ListObjectsV2 response in XML or JSON format.

    XML Example:
    <ListBucketResult>
        <IsTruncated>false</IsTruncated>
        <Contents>
            <Key>my-image.jpg</Key>
            <LastModified>2024-01-01T00:00:00.000Z</LastModified>
            <ETag>"fba9dede5f27731c9771645a39863328"</ETag>
            <Size>434234</Size>
            <StorageClass>STANDARD</StorageClass>
        </Contents>
        <Name>mybucket</Name>
        <Prefix></Prefix>
        <Delimiter></Delimiter>
        <MaxKeys>1000</MaxKeys>
        <KeyCount>1</KeyCount>
    </ListBucketResult>

    JSON Example:
    {
        "name": "mybucket",
        "prefix": "",
        "delimiter": "",
        "maxKeys": 1000,
        "keyCount": 1,
        "isTruncated": false,
        "contents": [
            {
                "key": "my-image.jpg",
                "lastModified": "2024-01-01T00:00:00.000Z",
                "etag": "\"fba9dede5f27731c9771645a39863328\"",
                "size": 434234,
                "storageClass": "STANDARD"
            }
        ]
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'name': bucket,
            'prefix': prefix,
            'delimiter': delimiter,
            'maxKeys': max_keys,
            'keyCount': len(objects),
            'isTruncated': is_truncated,
            'contents': []
        }

        for obj in objects:
            data['contents'].append({
                'key': obj['name'],
                'lastModified': _format_datetime(obj.get('modified', datetime.utcnow())),
                'etag': obj.get('etag', f'"{obj["name"]}"'),
                'size': obj.get('size', 0),
                'storageClass': 'STANDARD'
            })

        if continuation_token:
            data['continuationToken'] = continuation_token
        if next_continuation_token:
            data['nextContinuationToken'] = next_continuation_token

        if common_prefixes:
            data['commonPrefixes'] = [{'prefix': p} for p in common_prefixes]

        return _to_json_response(data)

    # Default to XML
    root = _create_root('ListBucketResult')

    SubElement(root, 'IsTruncated').text = str(is_truncated).lower()

    for obj in objects:
        contents = SubElement(root, 'Contents')
        SubElement(contents, 'Key').text = obj['name']
        SubElement(contents, 'LastModified').text = _format_datetime(obj.get('modified', datetime.utcnow()))
        SubElement(contents, 'ETag').text = obj.get('etag', f'"{obj["name"]}"')
        SubElement(contents, 'Size').text = str(obj.get('size', 0))
        SubElement(contents, 'StorageClass').text = 'STANDARD'

    SubElement(root, 'Name').text = bucket
    SubElement(root, 'Prefix').text = prefix
    SubElement(root, 'Delimiter').text = delimiter
    SubElement(root, 'MaxKeys').text = str(max_keys)
    SubElement(root, 'KeyCount').text = str(len(objects))

    if continuation_token:
        SubElement(root, 'ContinuationToken').text = continuation_token
    if next_continuation_token:
        SubElement(root, 'NextContinuationToken').text = next_continuation_token

    if common_prefixes:
        for prefix_str in common_prefixes:
            cp = SubElement(root, 'CommonPrefixes')
            SubElement(cp, 'Prefix').text = prefix_str

    return _to_xml_response(root)


def create_bucket_response(location: str) -> Response:
    """
    Generate CreateBucket response.

    Returns empty body with Location header.
    """
    return Response(
        '',
        status=200,
        headers={'Location': location}
    )


def delete_response() -> Response:
    """Generate successful delete response (204 No Content)"""
    return Response('', status=204)


def head_response(content_length: int = 0, content_type: str = 'application/octet-stream',
                  etag: str = '', last_modified: str = '',
                  metadata: Dict = None) -> Response:
    """
    Generate HEAD response with metadata headers.
    """
    headers = {
        'Content-Length': str(content_length),
        'Content-Type': content_type,
        'Accept-Ranges': 'bytes'
    }

    if etag:
        headers['ETag'] = etag
    if last_modified:
        headers['Last-Modified'] = last_modified

    # Add custom metadata headers (x-amz-meta-*)
    if metadata:
        for key, value in metadata.items():
            headers[f'x-amz-meta-{key}'] = value

    return Response('', status=200, headers=headers)


def initiate_multipart_upload_response(bucket: str, key: str,
                                       upload_id: str) -> Response:
    """
    Generate InitiateMultipartUpload response in XML or JSON format.

    XML Example:
    <InitiateMultipartUploadResult>
        <Bucket>mybucket</Bucket>
        <Key>mykey</Key>
        <UploadId>upload-id</UploadId>
    </InitiateMultipartUploadResult>

    JSON Example:
    {
        "bucket": "mybucket",
        "key": "mykey",
        "uploadId": "upload-id"
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'bucket': bucket,
            'key': key,
            'uploadId': upload_id
        }
        return _to_json_response(data)

    # Default to XML
    root = _create_root('InitiateMultipartUploadResult')
    SubElement(root, 'Bucket').text = bucket
    SubElement(root, 'Key').text = key
    SubElement(root, 'UploadId').text = upload_id

    return _to_xml_response(root)


def upload_part_response(etag: str) -> Response:
    """
    Generate UploadPart response.

    Returns ETag in header.
    """
    return Response(
        '',
        status=200,
        headers={'ETag': etag}
    )


def complete_multipart_upload_response(bucket: str, key: str,
                                       location: str, etag: str) -> Response:
    """
    Generate CompleteMultipartUpload response in XML or JSON format.

    XML Example:
    <CompleteMultipartUploadResult>
        <Location>http://example.com/bucket/key</Location>
        <Bucket>mybucket</Bucket>
        <Key>mykey</Key>
        <ETag>"etag"</ETag>
    </CompleteMultipartUploadResult>

    JSON Example:
    {
        "location": "http://example.com/bucket/key",
        "bucket": "mybucket",
        "key": "mykey",
        "etag": "\"etag\""
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'location': location,
            'bucket': bucket,
            'key': key,
            'etag': etag
        }
        return _to_json_response(data)

    # Default to XML
    root = _create_root('CompleteMultipartUploadResult')
    SubElement(root, 'Location').text = location
    SubElement(root, 'Bucket').text = bucket
    SubElement(root, 'Key').text = key
    SubElement(root, 'ETag').text = etag

    return _to_xml_response(root)


def list_parts_response(bucket: str, key: str, upload_id: str,
                        parts: List[Dict], is_truncated: bool = False,
                        next_part_number_marker: int = 0,
                        max_parts: int = 1000) -> Response:
    """
    Generate ListParts response in XML or JSON format.

    XML Example:
    <ListPartsResult>
        <Bucket>mybucket</Bucket>
        <Key>mykey</Key>
        <UploadId>upload-id</UploadId>
        <IsTruncated>false</IsTruncated>
        <Part>
            <PartNumber>1</PartNumber>
            <LastModified>2024-01-01T00:00:00.000Z</LastModified>
            <ETag>"etag"</ETag>
            <Size>5242880</Size>
        </Part>
        <MaxParts>1000</MaxParts>
    </ListPartsResult>

    JSON Example:
    {
        "bucket": "mybucket",
        "key": "mykey",
        "uploadId": "upload-id",
        "isTruncated": false,
        "maxParts": 1000,
        "parts": [
            {
                "partNumber": 1,
                "lastModified": "2024-01-01T00:00:00.000Z",
                "etag": "\"etag\"",
                "size": 5242880
            }
        ]
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'bucket': bucket,
            'key': key,
            'uploadId': upload_id,
            'isTruncated': is_truncated,
            'maxParts': max_parts,
            'parts': []
        }

        for part in parts:
            data['parts'].append({
                'partNumber': part['part_number'],
                'lastModified': _format_datetime(part.get('last_modified', datetime.utcnow())),
                'etag': part['etag'],
                'size': part['size']
            })

        if next_part_number_marker:
            data['nextPartNumberMarker'] = next_part_number_marker

        return _to_json_response(data)

    # Default to XML
    root = _create_root('ListPartsResult')
    SubElement(root, 'Bucket').text = bucket
    SubElement(root, 'Key').text = key
    SubElement(root, 'UploadId').text = upload_id
    SubElement(root, 'IsTruncated').text = str(is_truncated).lower()

    for part in parts:
        part_elem = SubElement(root, 'Part')
        SubElement(part_elem, 'PartNumber').text = str(part['part_number'])
        SubElement(part_elem, 'LastModified').text = _format_datetime(part.get('last_modified', datetime.utcnow()))
        SubElement(part_elem, 'ETag').text = part['etag']
        SubElement(part_elem, 'Size').text = str(part['size'])

    if next_part_number_marker:
        SubElement(root, 'NextPartNumberMarker').text = str(next_part_number_marker)

    SubElement(root, 'MaxParts').text = str(max_parts)

    return _to_xml_response(root)


def copy_object_response(etag: str, last_modified: datetime) -> Response:
    """
    Generate CopyObject response in XML or JSON format.

    XML Example:
    <CopyObjectResult>
        <ETag>"etag"</ETag>
        <LastModified>2024-01-01T00:00:00.000Z</LastModified>
    </CopyObjectResult>

    JSON Example:
    {
        "etag": "\"etag\"",
        "lastModified": "2024-01-01T00:00:00.000Z"
    }
    """
    output_format = _get_output_format()

    if output_format == 'json':
        data = {
            'etag': etag,
            'lastModified': _format_datetime(last_modified)
        }
        return _to_json_response(data)

    # Default to XML
    root = _create_root('CopyObjectResult')
    SubElement(root, 'ETag').text = etag
    SubElement(root, 'LastModified').text = _format_datetime(last_modified)

    return _to_xml_response(root)


def put_object_response(etag: str, version_id: str = '') -> Response:
    """
    Generate PutObject response.

    Returns ETag in header.
    """
    headers = {'ETag': etag}
    if version_id:
        headers['x-amz-version-id'] = version_id

    return Response('', status=200, headers=headers)


def get_object_response(body: bytes, content_type: str = 'application/octet-stream',
                        content_length: int = None, etag: str = '',
                        last_modified: str = '', metadata: Dict = None) -> Response:
    """
    Generate GetObject response with body and headers.
    """
    if content_length is None:
        content_length = len(body)

    headers = {
        'Content-Type': content_type,
        'Content-Length': str(content_length),
        'Accept-Ranges': 'bytes'
    }

    if etag:
        headers['ETag'] = etag
    if last_modified:
        headers['Last-Modified'] = last_modified

    # Add custom metadata headers
    if metadata:
        for key, value in metadata.items():
            headers[f'x-amz-meta-{key}'] = value

    return Response(body, status=200, headers=headers)
