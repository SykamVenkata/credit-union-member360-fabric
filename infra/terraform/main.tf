terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    fabric  = { source = "microsoft/fabric", version = "~> 1.0" }
  }
  backend "azurerm" {} # -backend-config=env/dev.backend.hcl
}

provider "azurerm" {
  features {}
}

provider "fabric" {}

locals {
  name = "member360-${var.environment}"
  tags = merge(var.tags, { environment = var.environment, workload = "member-360" })
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# Fabric capacity: pause outside business hours in dev to control cost
resource "azurerm_fabric_capacity" "this" {
  name                   = replace("fc${local.name}", "-", "")
  resource_group_name    = azurerm_resource_group.this.name
  location               = var.location
  administration_members = var.capacity_admins
  sku {
    name = var.capacity_sku
    tier = "Fabric"
  }
  tags = local.tags
}

data "fabric_capacity" "this" {
  display_name = azurerm_fabric_capacity.this.name
  depends_on   = [azurerm_fabric_capacity.this]
}

resource "fabric_workspace" "this" {
  display_name = "Member 360 (${var.environment})"
  description  = "Credit union Member 360: identity resolution, features, scoring and BI"
  capacity_id  = data.fabric_capacity.this.id
}

resource "fabric_lakehouse" "member360" {
  display_name = "lh_member360"
  workspace_id = fabric_workspace.this.id
  configuration = {
    enable_schemas = true
  }
}

resource "fabric_warehouse" "member360" {
  display_name = "wh_member360"
  workspace_id = fabric_workspace.this.id
}

resource "fabric_environment" "python" {
  display_name = "env_member360"
  workspace_id = fabric_workspace.this.id
  description  = "Spark environment with the creditunion wheel attached"
}

resource "fabric_workspace_role_assignment" "engineers" {
  workspace_id = fabric_workspace.this.id
  principal = {
    id   = var.engineers_group_id
    type = "Group"
  }
  role = "Contributor"
}

resource "fabric_workspace_role_assignment" "analysts" {
  workspace_id = fabric_workspace.this.id
  principal = {
    id   = var.analysts_group_id
    type = "Group"
  }
  role = "Viewer"
}
