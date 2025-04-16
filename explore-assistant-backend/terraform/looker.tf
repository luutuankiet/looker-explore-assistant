terraform {
  required_providers {
    looker = {
      source  = "devoteamgcloud/looker"
      version = "0.4.1-beta"
    }
  }
}

provider "looker" {
  base_url      = var.looker_api_url
  client_id     = var.looker_client_id
  client_secret = var.looker_client_secret
}


# caveat : in order to have a flag to enable the deployment, needs to explicitly include this count param in each of the sub resource here.
#   count        = var.deploy_looker_projects ? 1 : 0


data "local_file" "cr_sa_key" {
  filename   = "${path.root}/cloud_run/explore_assistant_sa_key.json"
  depends_on = [module.cloud_run_backend.google_service_account_key]
}


# to read it : jsondecode(data.local_file.cr_sa_key.content)..... 
locals {
  username    = jsondecode(data.local_file.cr_sa_key.content).client_email
  host        = jsondecode(data.local_file.cr_sa_key.content).project_id
  database    = var.dataset_id_name
  certificate = base64encode(data.local_file.cr_sa_key.content)


  depends_on = [data.local_file.cr_sa_key]

}



resource "looker_connection" "looker_bq_connection" {
  count        = var.deploy_looker_projects ? 1 : 0
  name         = var.looker_connection_name
  dialect_name = "bigquery_standard_sql"
  host         = local.host
  certificate  = local.certificate
  file_type    = ".json"
  database     = local.database
  db_timezone  = "UTC"
}

resource "looker_project" "explore_assistant_poc_extension_project" {
  count              = var.deploy_looker_projects ? 1 : 0
  name               = var.looker_extension_project_name
  rename_when_delete = true
}

resource "looker_project" "explore_assistant_performance_monitoring_project" {
  count              = var.deploy_looker_projects ? 1 : 0
  name               = var.looker_performance_monitoring_project_name
  rename_when_delete = true
}


resource "looker_lookml_model" "explore_assistant_extension_model" {
  count                       = var.deploy_looker_projects ? 1 : 0
  name                        = var.looker_extension_project_name
  project_name                = var.looker_extension_project_name
  allowed_db_connection_names = [looker_connection.looker_bq_connection[0].name]
  depends_on                  = [looker_project.explore_assistant_poc_extension_project]
}

resource "looker_lookml_model" "explore_assistant_performance_monitoring_model" {
  count                       = var.deploy_looker_projects ? 1 : 0
  name                        = var.looker_performance_monitoring_project_name
  project_name                = var.looker_performance_monitoring_project_name
  allowed_db_connection_names = [looker_connection.looker_bq_connection[0].name]
  depends_on                  = [looker_project.explore_assistant_performance_monitoring_project]
}