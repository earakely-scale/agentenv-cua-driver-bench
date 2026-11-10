"""launch.py N TYPE [--kvm] [--volume-gb GB]: N worker VMs of instance type TYPE, set up by user-data.sh; prints their
instance ids. ``--kvm`` turns on nested virtualization, which a Windows or an Omarchy run's computers need, booted as
disks under KVM (a c8i, say). The AWS CLI 2.32 refuses that setting, so this goes through boto3, which takes it from
botocore 1.43. Its settings come from the environment, else tools/fleet/fleet.env (see fleet.env.example)."""
import argparse
import re

import boto3

from common import HERE, setting

AMI = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
#: The framework the workers install unless FLEET_FRAMEWORK names another: the first the bench's Omarchy row ran on.
FRAMEWORK = "agentenv-framework==0.9.1500"
BENCH_REPO = "https://github.com/earakely-scale/agentenv-cua-driver-bench"
#: FLEET_TAGS' form, the AWS CLI's: {Key=k,Value=v},{Key=k2,Value=v2}.
TAG = re.compile(r"\{Key=([^,}]+),Value=([^}]*)\}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("count", type=int)
    parser.add_argument("type")
    parser.add_argument("--kvm", action="store_true", help="nested virtualization, for Windows and Omarchy computers")
    parser.add_argument("--volume-gb", type=int, default=150)
    args = parser.parse_args()
    session = boto3.Session(region_name=setting("FLEET_REGION"))
    ami = session.client("ssm").get_parameter(Name=AMI)["Parameter"]["Value"]
    reply = session.client("ec2").run_instances(**request(args.count, args.type, ami, args.kvm, args.volume_gb))
    print(" ".join(instance["InstanceId"] for instance in reply["Instances"]))


def request(count, instance_type, ami, kvm=False, volume_gb=150):
    """run_instances' arguments for ``count`` workers of ``instance_type`` from ``ami``: set up by user-data.sh with
    the framework, the bench and the hours before each shuts itself down, and so terminates; with ``kvm``, nested
    virtualization."""
    data = (HERE / "user-data.sh").read_text()
    for key, value in (("@FRAMEWORK@", setting("FLEET_FRAMEWORK", FRAMEWORK)),
                       ("@BENCH_REPO@", setting("FLEET_BENCH_REPO", BENCH_REPO)),
                       ("@MAX_MINUTES@", str(int(setting("FLEET_MAX_HOURS", "12")) * 60))):
        data = data.replace(key, value)
    tags = [{"Key": "Name", "Value": setting("FLEET_NAME", "cua-driver-bench-fleet")}]
    tags += [{"Key": key, "Value": value} for key, value in TAG.findall(setting("FLEET_TAGS", ""))]
    return {"ImageId": ami, "InstanceType": instance_type, "MinCount": count, "MaxCount": count,
            "SubnetId": setting("FLEET_SUBNET"), "SecurityGroupIds": setting("FLEET_SECURITY_GROUPS").split(),
            "IamInstanceProfile": {"Name": setting("FLEET_INSTANCE_PROFILE")},
            "InstanceInitiatedShutdownBehavior": "terminate",
            "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": volume_gb, "VolumeType": "gp3"}}],
            "UserData": data, "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}],
            **({"CpuOptions": {"NestedVirtualization": "enabled"}} if kvm else {})}


if __name__ == "__main__":
    main()
