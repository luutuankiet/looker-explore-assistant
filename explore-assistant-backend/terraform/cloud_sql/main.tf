variable "deployment_region" {
  type        = string
  description = "Region to deploy the Cloud SQL service. Example: us-central1"
}

variable "project_id" {
  type = string
}

variable "root_password" {
  type = string
}

variable "user_password" {
  type = string
}

variable "cloudSQL_server_name" {
  type = string
}

terraform {
  required_version = "~> 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google",
      version = ">= 3.43.0, < 5.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}

resource "google_compute_global_address" "private_ip_address" {
  project = var.project_id
  name          = "cloud-sql-private-ip-address"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = "projects/jtc-test-looker-core/global/networks/looker-psc-southbound-https"
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = "projects/jtc-test-looker-core/global/networks/looker-psc-southbound-https"
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}

resource "google_sql_database_instance" "main" {
  depends_on = [google_service_networking_connection.private_vpc_connection]
  database_version     = "MYSQL_8_0_31"
  deletion_protection  = false
  encryption_key_name  = null
  instance_type        = "CLOUD_SQL_INSTANCE"
  master_instance_name = null
  name                 = var.cloudSQL_server_name #input your instance name
  project              = var.project_id
  region               = var.deployment_region
  root_password        = var.root_password # sensitive
  settings {
    activation_policy           = "ALWAYS"
    availability_type           = "ZONAL"
    collation                   = null
    connector_enforcement       = "NOT_REQUIRED"
    deletion_protection_enabled = false
    disk_autoresize             = true
    disk_autoresize_limit       = 0
    disk_size                   = 10
    disk_type                   = "PD_SSD"
    edition                     = "ENTERPRISE"
    pricing_plan                = "PER_USE"
    tier                        = "db-custom-2-8192"
    time_zone                   = null
    user_labels                 = {}
    backup_configuration {
      binary_log_enabled             = true
      enabled                        = true
      location                       = "asia"
      point_in_time_recovery_enabled = false
      start_time                     = "05:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }
    insights_config {
      query_insights_enabled  = false
      query_plans_per_minute  = 0
      record_application_tags = false
      record_client_address   = false
    }
    ip_configuration {
      allocated_ip_range                            = null
      enable_private_path_for_google_cloud_services = true
      ipv4_enabled                                  = true
      private_network                               = "projects/jtc-test-looker-core/global/networks/looker-psc-southbound-https"
      authorized_networks {
        expiration_time = null
        name            = null
        value           = "0.0.0.0/0"
      }
    }
    location_preference {
      follow_gae_application = null
      secondary_zone         = null
      zone                   = "asia-southeast1-c"
    }
    maintenance_window {
      day          = 1
      hour         = 0
      update_track = "canary"
    }
    password_validation_policy {
      complexity                  = "COMPLEXITY_DEFAULT"
      disallow_username_substring = false
      enable_password_policy      = true
      min_length                  = 0
      password_change_interval    = null
      reuse_interval              = 0
    }
  }
  timeouts {
    create = null
    delete = null
    update = null
  }
}


# Create production database
resource "google_sql_database" "production" {
  name     = "production"
  project  = var.project_id
  instance = google_sql_database_instance.main.name
}

// Create cloud sql user
resource "google_sql_user" "cloud_sql_user" {
  name       = "cloud_sql_user"
  project    = var.project_id
  instance   = google_sql_database_instance.main.name
  host       = "%"
  password   = var.user_password
  depends_on = [google_sql_database.production]
}

output "cloudsql_instance_info" {
  value = {
    public_ip = google_sql_database_instance.main.public_ip_address
    username  = google_sql_user.cloud_sql_user.name
    password  = google_sql_user.cloud_sql_user.password
    database  = google_sql_database.production.name
  }
  sensitive  = true
  depends_on = [google_sql_user.cloud_sql_user]
}

resource "local_file" "cloudsql_outputs" {
  filename = "${path.module}/cloudsql_outputs.json"
  content = jsonencode({
    cloudsql_instance_info = {
      value = {
        public_ip = google_sql_database_instance.main.public_ip_address
        username  = google_sql_user.cloud_sql_user.name
        password  = google_sql_user.cloud_sql_user.password
        database  = google_sql_database.production.name
      }
    }
  })
  file_permission = "0600" # Restricted file permissions for security
  depends_on      = [google_sql_user.cloud_sql_user]
}
resource "null_resource" "generate_sql_schema" {
  triggers = {
    model_hash = fileexists("${path.module}/../../../explore-assistant-cloud-run/models.py") ? filesha256("${path.module}/../../../explore-assistant-cloud-run/models.py") : "no_models"
    script_hash = fileexists("${path.module}/create_tables.py") ? filesha256("${path.module}/create_tables.py") : "no_script"
  }

  provisioner "local-exec" {
    command = <<-EOT
      python -m venv .venv
      source .venv/bin/activate
      pip install sqlmodel pymysql
      
      # Set environment variables for database connection
      export DB_HOST="127.0.0.1"
      export DB_USER="${google_sql_user.cloud_sql_user.name}"
      export DB_PASS="${google_sql_user.cloud_sql_user.password}"
      export DB_NAME="${google_sql_database.production.name}"
      
      # Download and start Cloud SQL Proxy
      curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
      chmod +x cloud-sql-proxy
      ./cloud-sql-proxy ${google_sql_database_instance.main.connection_name} &
      sleep 10
      
      # Run the create_tables script
      python create_tables.py
      
      # Cleanup
      pkill cloud-sql-proxy
    EOT
    interpreter = ["bash", "-c"]
    working_dir = path.module
  }

  depends_on = [
    google_sql_database.production,
    google_sql_user.cloud_sql_user,
  ]
}
