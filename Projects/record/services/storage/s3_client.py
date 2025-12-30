import os
import boto3
from botocore.exceptions import ClientError


def s3_client():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def upload_fileobj(*, fileobj, bucket: str, key: str, content_type: str) -> None:
    try:
        s3_client().upload_fileobj(
            fileobj,
            bucket,
            key,
            ExtraArgs={"ContentType": content_type or "image/jpeg"},
        )
    except ClientError as e:
        raise RuntimeError(f"S3 upload failed: {e}") from e
