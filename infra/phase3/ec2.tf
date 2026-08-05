# EC2 web tier for the wedding site.
#
#   * AMI: latest AL2023 x86_64 kernel-6.1, resolved via the AWS-published
#     SSM parameter so we track security patches without hardcoding IDs.
#   * Instance: t3.micro in the public subnet, EC2 SG, IAM instance
#     profile granting S3 + SSM param reads + SSM Session Manager.
#     IMDSv2 required (http_tokens = "required") so credential harvesting
#     via SSRF against the metadata service fails.
#   * EIP: allocated separately + associated after boot. Keeping the EIP
#     out of aws_instance's implicit lifecycle means an instance replace
#     (AMI bump, size change) keeps the same public IP -- Session 14's
#     CloudFront origin doesn't shift under us.
#   * user_data: renders templates/user_data.sh.tftpl. It installs deps,
#     clones the repo, fetches SSM params, migrates, collectstatic-s,
#     starts gunicorn + nginx. Idempotent-ish and self-logging to
#     /var/log/user-data.log.
#
# user_data_replace_on_change = false: we intentionally do NOT want a
# script tweak to recreate the instance. If we edit the bootstrap and
# need it re-run, SSM into the box and run it manually (or rebuild via
# terraform apply -replace=aws_instance.web).

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
}

resource "aws_eip" "web" {
  domain = "vpc"

  tags = {
    Name = "${var.project_tag}-web-eip"
  }
}

resource "aws_instance" "web" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  user_data = templatefile("${path.module}/templates/user_data.sh.tftpl", {
    app_dir    = "/home/ec2-user/aws-wedding-website"
    repo_url   = "https://github.com/stnielse/aws-wedding-website.git"
    ssm_prefix = local.ssm_prefix
    aws_region = "us-east-1"
    gunicorn_service = templatefile("${path.module}/templates/gunicorn.service.tftpl", {
      app_dir = "/home/ec2-user/aws-wedding-website"
    })
    nginx_main = file("${path.module}/templates/nginx-main.conf.tftpl")
    nginx_conf = file("${path.module}/templates/nginx-site.conf.tftpl")
  })
  user_data_replace_on_change = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name = "${var.project_tag}-web"
  }

  # Every SSM parameter user_data reads must exist before the instance
  # boots. aws_eip.web is already implicitly ordered ahead of the
  # instance via aws_ssm_parameter.allowed_hosts (which references
  # aws_eip.web.public_ip). RDS must be reachable so the first
  # migrate call succeeds.
  depends_on = [
    aws_db_instance.wedding,
    aws_ssm_parameter.django_secret_key,
    aws_ssm_parameter.db_password,
    aws_ssm_parameter.db_host,
    aws_ssm_parameter.db_port,
    aws_ssm_parameter.db_name,
    aws_ssm_parameter.db_user,
    aws_ssm_parameter.domain,
    aws_ssm_parameter.allowed_hosts,
    aws_ssm_parameter.aws_region,
    aws_ssm_parameter.aws_storage_bucket_name,
    aws_ssm_parameter.aws_static_bucket_name,
    aws_ssm_parameter.aws_s3_custom_domain,
    aws_ssm_parameter.aws_static_custom_domain,
    aws_ssm_parameter.csrf_trusted_origins,
  ]
}

resource "aws_eip_association" "web" {
  instance_id   = aws_instance.web.id
  allocation_id = aws_eip.web.id
}
