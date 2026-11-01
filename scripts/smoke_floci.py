"""Exercise local Floci EC2/VPC/EBS API contracts, never the AWS service.

Explicit endpoint allowlist and explicit fictional credentials prevent an AWS
profile, instance role, environment credentials or proxy from being used.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def local_endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or not parsed.port
    ):
        raise ValueError(
            "Usa un endpoint HTTP local explícito con puerto, sin credenciales ni ruta"
        )
    hostname = parsed.hostname
    allowed = hostname in {"localhost", "floci"}
    if not allowed:
        try:
            allowed = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
    if not allowed:
        raise ValueError(
            "Sólo se permiten loopback o el servicio Compose floci; AWS está prohibido"
        )
    return value.rstrip("/")


def run(endpoint="http://127.0.0.1:4566", *, region="us-east-1"):
    endpoint = local_endpoint(endpoint)
    session = boto3.session.Session(
        aws_access_key_id="test", aws_secret_access_key="test", region_name=region
    )
    ec2 = session.client(
        "ec2",
        endpoint_url=endpoint,
        config=Config(connect_timeout=2, read_timeout=10, retries={"max_attempts": 0}, proxies={}),
    )
    token = "agil-smoke-" + uuid4().hex[:12]
    report = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "region": region,
        "execution": "local_floci_ec2_mock",
        "checks": [],
        "cleanup": [],
        "limitations": [
            "No ejecuta una VM ni contenedores EC2 invitados",
            "EBS y red prueban contratos/metadatos, no filesystem, paquetes, IOPS ni conectividad",
            "No prueba capacidad, IAM real, EC2, Cloudflare, WhatsApp u OpenAI",
        ],
    }
    cleanup = []

    def check(name, valid):
        report["checks"].append({"name": name, "status": "passed" if valid else "failed"})
        if not valid:
            raise AssertionError(name)

    def defer(name, action, **kwargs):
        cleanup.append((name, action, kwargs))

    try:
        zones = ec2.describe_availability_zones()["AvailabilityZones"]
        check("describe_availability_zones", bool(zones))
        zone = zones[0]["ZoneName"]
        vpc = ec2.create_vpc(CidrBlock="10.234.0.0/16")["Vpc"]["VpcId"]
        defer("delete_vpc", ec2.delete_vpc, VpcId=vpc)
        subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.234.1.0/24", AvailabilityZone=zone)[
            "Subnet"
        ]["SubnetId"]
        defer("delete_subnet", ec2.delete_subnet, SubnetId=subnet)
        group = ec2.create_security_group(
            GroupName=token, Description="Fictional local API smoke", VpcId=vpc
        )["GroupId"]
        defer("delete_security_group", ec2.delete_security_group, GroupId=group)
        ec2.authorize_security_group_ingress(
            GroupId=group,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "127.0.0.1/32"}],
                }
            ],
        )
        groups = ec2.describe_security_groups(GroupIds=[group])["SecurityGroups"]
        check(
            "vpc_subnet_security_group",
            groups[0]["VpcId"] == vpc
            and any(rule.get("FromPort") == 443 for rule in groups[0]["IpPermissions"]),
        )
        instance = ec2.run_instances(
            ImageId="ami-alpine",
            InstanceType="t3.micro",
            MinCount=1,
            MaxCount=1,
            SubnetId=subnet,
            SecurityGroupIds=[group],
            ClientToken=token,
            MetadataOptions={"HttpTokens": "required"},
            TagSpecifications=[
                {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": token}]}
            ],
        )["Instances"][0]["InstanceId"]
        defer("terminate_instances", ec2.terminate_instances, InstanceIds=[instance])
        ec2.get_waiter("instance_running").wait(
            InstanceIds=[instance], WaiterConfig={"Delay": 1, "MaxAttempts": 10}
        )
        described = ec2.describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][
            0
        ]
        check(
            "run_describe_instance",
            described["SubnetId"] == subnet and described["State"]["Name"] == "running",
        )
        volume = ec2.create_volume(AvailabilityZone=zone, Size=1, VolumeType="gp3", Encrypted=True)[
            "VolumeId"
        ]
        defer("delete_volume", ec2.delete_volume, VolumeId=volume)
        ec2.get_waiter("volume_available").wait(
            VolumeIds=[volume], WaiterConfig={"Delay": 1, "MaxAttempts": 10}
        )
        ec2.attach_volume(VolumeId=volume, InstanceId=instance, Device="/dev/sdf")
        defer("detach_volume", ec2.detach_volume, VolumeId=volume, InstanceId=instance, Force=True)
        ec2.get_waiter("volume_in_use").wait(
            VolumeIds=[volume], WaiterConfig={"Delay": 1, "MaxAttempts": 10}
        )
        attached = ec2.describe_volumes(VolumeIds=[volume])["Volumes"][0]
        check(
            "create_attach_encrypted_volume",
            attached["Encrypted"] and attached["Attachments"][0]["InstanceId"] == instance,
        )
        try:
            snapshot = ec2.create_snapshot(VolumeId=volume, Description=token)["SnapshotId"]
            defer("delete_snapshot", ec2.delete_snapshot, SnapshotId=snapshot)
            ec2.get_waiter("snapshot_completed").wait(
                SnapshotIds=[snapshot], WaiterConfig={"Delay": 1, "MaxAttempts": 10}
            )
            restored = ec2.create_volume(
                AvailabilityZone=zone, SnapshotId=snapshot, VolumeType="gp3"
            )["VolumeId"]
            defer("delete_restored_volume", ec2.delete_volume, VolumeId=restored)
            ec2.get_waiter("volume_available").wait(
                VolumeIds=[restored], WaiterConfig={"Delay": 1, "MaxAttempts": 10}
            )
            restored_view = ec2.describe_volumes(VolumeIds=[restored])["Volumes"][0]
            check(
                "snapshot_restore_metadata",
                restored_view["Size"] == 1 and restored_view["SnapshotId"] == snapshot,
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "UnsupportedOperation":
                raise
            report["checks"].append(
                {
                    "name": "snapshot_restore_metadata",
                    "status": "unsupported",
                    "code": "UnsupportedOperation",
                }
            )
            report["limitations"].append(
                "CreateSnapshot no está soportado para el volumen de este perfil EC2 mock; restore no verificado"
            )
    except (BotoCoreError, ClientError, AssertionError) as error:
        report["failure"] = {
            "type": type(error).__name__,
            "code": error.response.get("Error", {}).get("Code", "unknown")
            if isinstance(error, ClientError)
            else "local_smoke_failed",
        }
    finally:
        # Reverse dependency order; this only deletes the resources this run created.
        for name, action, kwargs in reversed(cleanup):
            try:
                action(**kwargs)
                if name == "detach_volume":
                    ec2.get_waiter("volume_available").wait(
                        VolumeIds=[kwargs["VolumeId"]], WaiterConfig={"Delay": 1, "MaxAttempts": 10}
                    )
                if name == "terminate_instances":
                    ec2.get_waiter("instance_terminated").wait(
                        InstanceIds=kwargs["InstanceIds"],
                        WaiterConfig={"Delay": 1, "MaxAttempts": 10},
                    )
                report["cleanup"].append({"name": name, "status": "passed"})
            except (BotoCoreError, ClientError):
                report["cleanup"].append({"name": name, "status": "failed"})
        ec2.close()
    clean = "failure" not in report and all(
        item["status"] == "passed" for item in report["cleanup"]
    )
    limited = any(item["status"] == "unsupported" for item in report["checks"])
    report["status"] = ("passed_with_limitations" if limited else "passed") if clean else "failed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:4566")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    try:
        result = run(args.endpoint, region=args.region)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"passed", "passed_with_limitations"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
