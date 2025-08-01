variable "bq_cloudsql_connection_id" {
  type        = string
  description = "name of the external bigquery connection to cloud sql"

}

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

variable "dataset_id_name" {
  type    = string
  default = "explore_assistant"
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

resource "google_sql_database_instance" "main" {
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
      enable_private_path_for_google_cloud_services = false
      ipv4_enabled                                  = true
      private_network                               = null
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




# Create secrets for Cloud SQL credentials
resource "google_secret_manager_secret" "cloud_sql_host" {
  project   = var.project_id
  secret_id = format("looker-genai-cloud-sql-host-%s", var.cloudSQL_server_name)

  replication {
    auto {
    }
  }

}

resource "google_secret_manager_secret" "cloud_sql_user" {
  project   = var.project_id
  secret_id = format("looker-genai-cloud-sql-user-%s", var.cloudSQL_server_name)

  replication {
    auto {
    }
  }

}

resource "google_secret_manager_secret" "cloud_sql_password" {
  project   = var.project_id
  secret_id = format("looker-genai-cloud-sql-password-%s", var.cloudSQL_server_name)

  replication {
    auto {
    }
  }

}

resource "google_secret_manager_secret" "cloud_sql_database" {
  project   = var.project_id
  secret_id = format("looker-genai-cloud-sql-database-%s", var.cloudSQL_server_name)

  replication {
    auto {
    }
  }

}


# Create secret versions with actual values
resource "google_secret_manager_secret_version" "cloud_sql_host_version" {
  secret      = google_secret_manager_secret.cloud_sql_host.id
  secret_data = google_sql_database_instance.main.public_ip_address

  depends_on = [
    google_secret_manager_secret.cloud_sql_host,
    google_sql_database_instance.main
  ]
}

resource "google_secret_manager_secret_version" "cloud_sql_user_version" {
  secret      = google_secret_manager_secret.cloud_sql_user.id
  secret_data = google_sql_user.cloud_sql_user.name

  depends_on = [
    google_secret_manager_secret.cloud_sql_user,
    google_sql_user.cloud_sql_user
  ]
}

resource "google_secret_manager_secret_version" "cloud_sql_password_version" {
  secret      = google_secret_manager_secret.cloud_sql_password.id
  secret_data = google_sql_user.cloud_sql_user.password

  depends_on = [
    google_secret_manager_secret.cloud_sql_password,
    google_sql_user.cloud_sql_user
  ]
}

resource "google_secret_manager_secret_version" "cloud_sql_database_version" {
  secret      = google_secret_manager_secret.cloud_sql_database.id
  secret_data = google_sql_database.production.name

  depends_on = [
    google_secret_manager_secret.cloud_sql_database,
    google_sql_database.production
  ]
}


resource "google_bigquery_connection" "bq_cloud_sql_connection" {
  connection_id = var.bq_cloudsql_connection_id
  project       = var.project_id
  location      = var.deployment_region

  cloud_sql {
    instance_id = google_sql_database_instance.main.connection_name
    database    = google_sql_database.production.name
    type        = split("_", google_sql_database_instance.main.database_version)[0]
    credential {
      username = google_sql_user.cloud_sql_user.name
      password = google_sql_user.cloud_sql_user.password
    }
  }

  depends_on = [
    google_sql_database_instance.main,
    google_sql_database.production
  ]
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

resource "null_resource" "run_python" {
  triggers = {
    cloudsql_info_changes = local_file.cloudsql_outputs.content # Trigger on content changes
  }

  provisioner "local-exec" {
    working_dir = path.module
    command     = <<-EOT
    python -m venv .venv && \
    source .venv/bin/activate && \
    python -m pip install -r requirements.txt && \
    python create_tables.py
    EOT
    interpreter = ["bash", "-c"]
  }

  depends_on = [local_file.cloudsql_outputs]
}

# Read the table_names.json file created by the Python script
data "local_file" "table_names" {
  filename   = "${path.module}/table_names.json"
  depends_on = [null_resource.run_python]
}

locals {
  # Parse the table names from the JSON file
  tables = jsondecode(data.local_file.table_names.content).tables

  # Create the fully qualified connection ID
  connection_id = format("%s.%s.%s",
    google_bigquery_connection.bq_cloud_sql_connection.project,
    google_bigquery_connection.bq_cloud_sql_connection.location,
    google_bigquery_connection.bq_cloud_sql_connection.connection_id
  )

  # Generate SQL statements for each table
  view_queries = [for table in local.tables :
    "CREATE OR REPLACE VIEW `${var.project_id}.${var.dataset_id_name}.${table}` AS SELECT * FROM EXTERNAL_QUERY('${local.connection_id}', 'SELECT * FROM ${table}');"
  ]

  # Combine all queries into a single SQL script
  combined_query = join("\n", local.view_queries)
}

# Create BigQuery job to create views
resource "google_bigquery_job" "create_bq_cloudsql_views" {
  job_id = "create_bq_cloudsql_views-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  query {
    query              = local.combined_query
    create_disposition = ""
    write_disposition  = ""
  }

  location = var.deployment_region

  lifecycle {
    ignore_changes = [query, job_id]
  }

  depends_on = [
    data.local_file.table_names,
    google_bigquery_connection.bq_cloud_sql_connection
  ]
}
