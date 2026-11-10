"""launch.py N TYPE [--nested]: launch.sh's N worker VMs of instance type TYPE, set up by user-data.sh, through boto3;
prints their instance ids. Its settings are launch.sh's, from the environment, else tools/fleet/fleet.env, and
``FLEET_DISK_GB``, the root volume's size (150 GB; a Windows run's four computers want 250). ``--nested``
turns on nested virtualization, which a Windows run's VMs need for the KVM its computers boot under (on c8i, m8i or
r8i), and which AWS CLI 2.32 can't ask for."""
import argparse
import os

import boto3

from common import HERE, setting

AMI = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"


def tags():
    """FLEET_NAME and FLEET_TAGS, launch.sh's ``{Key=k,Value=v},...``, as the API takes them."""
    found = [{"Key": "Name", "Value": setting("FLEET_NAME", "cua-driver-bench-fleet")}]
    for tag in filter(None, os.environ.get("FLEET_TAGS", "").replace("},{", "}\n{").splitlines()):
        fields = dict(field.split("=", 1) for field in tag.strip("{}").split(","))
        found.append({"Key": fields["Key"], "Value": fields["Value"]})
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("count", type=int)
    parser.add_argument("type")
    parser.add_argument("--nested", action="store_true")
    args = parser.parse_args()
    data = ((HERE / "user-data.sh").read_text()
            .replace("@FRAMEWORK@", setting("FLEET_FRAMEWORK", "agentenv-framework==0.9.1412"))
            .replace("@BENCH_REPO@", setting("FLEET_BENCH_REPO", "https://github.com/earakely-scale/agentenv-cua-driver-bench"))
            .replace("@MAX_MINUTES@", str(int(setting("FLEET_MAX_HOURS", "12")) * 60)))
    session = boto3.Session(region_name=setting("FLEET_REGION"))
    ami = session.client("ssm").get_parameter(Name=AMI)["Parameter"]["Value"]
    started = session.client("ec2").run_instances(
        ImageId=ami, InstanceType=args.type, MinCount=args.count, MaxCount=args.count,
        SubnetId=setting("FLEET_SUBNET"), SecurityGroupIds=setting("FLEET_SECURITY_GROUPS").split(),
        IamInstanceProfile={"Name": setting("FLEET_INSTANCE_PROFILE")}, InstanceInitiatedShutdownBehavior="terminate",
        UserData=data, BlockDeviceMappings=[{"DeviceName": "/dev/sda1",
                              "Ebs": {"VolumeSize": int(setting("FLEET_DISK_GB", "150")), "VolumeType": "gp3"}}],
        TagSpecifications=[{"ResourceType": "instance", "Tags": tags()}],
        **({"CpuOptions": {"NestedVirtualization": "enabled"}} if args.nested else {}))
    print(" ".join(instance["InstanceId"] for instance in started["Instances"]))


if __name__ == "__main__":
    main()
