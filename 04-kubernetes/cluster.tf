# Filter AZs supported by EKS (usually a, b, c, d, f)
data "aws_availability_zones" "available" {
  state         = "available"
  exclude_names = ["us-east-1e"]
}

data "aws_subnets" "eks" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "availability-zone"
    values = data.aws_availability_zones.available.names
  }
}

# EKS Cluster Configuration
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "aiops-eks-cluster"
  cluster_version = "1.29"

  cluster_endpoint_public_access = true

  vpc_id                   = data.aws_vpc.default.id
  subnet_ids               = data.aws_subnets.eks.ids
  control_plane_subnet_ids = data.aws_subnets.eks.ids

  # EKS Managed Node Group
  eks_managed_node_groups = {
    aiops_nodes = {
      min_size     = 1
      max_size     = 2
      desired_size = 2

      instance_types = ["t3.small"]
      capacity_type  = "SPOT" # Save costs
    }
  }

  enable_cluster_creator_admin_permissions = true

  tags = {
    Environment = "test"
    ManagedBy   = "aiops"
  }
}

# Deploy a sample application to monitor
resource "kubernetes_namespace" "sample_app" {
  metadata {
    name = "aiops-sample"
  }
  depends_on = [module.eks]
}

resource "kubernetes_deployment" "bad_pod" {
  metadata {
    name      = "crashing-app"
    namespace = kubernetes_namespace.sample_app.metadata[0].name
    labels = {
      app = "crashing-app"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "crashing-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "crashing-app"
        }
      }

      spec {
        container {
          image = "nginx:latest"
          name  = "nginx"

          resources {
            limits = {
              cpu    = "0.5"
              memory = "512Mi"
            }
            requests = {
              cpu    = "250m"
              memory = "50Mi"
            }
          }
        }
      }
    }
  }

  wait_for_rollout = true
}
