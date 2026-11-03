#!/bin/bash
# launch.sh N TYPE: N worker VMs of instance type TYPE, set up by user-data.sh; prints their instance ids. Its
# settings come from the environment, else tools/fleet/fleet.env (see fleet.env.example).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
[ -f "$here/fleet.env" ] && { given=$(export -p); set -a; . "$here/fleet.env"; set +a; eval "$given"; }
: "${FLEET_REGION:?}" "${FLEET_SUBNET:?}" "${FLEET_SECURITY_GROUPS:?}" "${FLEET_INSTANCE_PROFILE:?}"
ami=$(aws ssm get-parameter --region "$FLEET_REGION" --query Parameter.Value --output text \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id)
data=$(mktemp)
trap 'rm -f "$data"' EXIT
sed -e "s|@FRAMEWORK@|${FLEET_FRAMEWORK:-agentenv-framework==0.9.1412}|" \
    -e "s|@BENCH_REPO@|${FLEET_BENCH_REPO:-https://github.com/earakely-scale/agentenv-cua-driver-bench}|" \
    -e "s|@MAX_MINUTES@|$(( ${FLEET_MAX_HOURS:-12} * 60 ))|" "$here/user-data.sh" > "$data"
aws ec2 run-instances --region "$FLEET_REGION" --count "$1" --image-id "$ami" --instance-type "$2" \
  --subnet-id "$FLEET_SUBNET" --security-group-ids $FLEET_SECURITY_GROUPS \
  --iam-instance-profile Name="$FLEET_INSTANCE_PROFILE" --instance-initiated-shutdown-behavior terminate \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=150,VolumeType=gp3}' --user-data "file://$data" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${FLEET_NAME:-cua-driver-bench-fleet}}${FLEET_TAGS:+,$FLEET_TAGS}]" \
  --query 'Instances[].InstanceId' --output text
