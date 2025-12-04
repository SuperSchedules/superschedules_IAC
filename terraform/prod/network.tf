resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "superschedules-prod-vpc"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "superschedules-prod-igw"
  }
}

resource "aws_subnet" "public" {
  for_each                = { for idx, cidr in var.public_subnet_cidrs : idx => cidr }
  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value
  map_public_ip_on_launch = true
  availability_zone       = element(data.aws_availability_zones.available.names, tonumber(each.key))

  tags = {
    Name = "superschedules-prod-public-${each.key}"
  }
}

# Private subnets removed - using public subnets only to eliminate NAT Gateway costs

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "superschedules-prod-public"
  }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# NAT Gateway, Elastic IP, and private route tables removed to save ~$45/month
# Instances now use public subnets with security groups for protection

