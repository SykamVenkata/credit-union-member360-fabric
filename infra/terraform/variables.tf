variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod"
  }
}

variable "location" {
  type    = string
  default = "westus2"
}

variable "capacity_sku" {
  type    = string
  default = "F2"
}

variable "capacity_admins" {
  type        = list(string)
  description = "UPNs of Fabric capacity administrators"
}

variable "engineers_group_id" {
  type        = string
  description = "Entra ID group object id for data engineers (workspace Contributor)"
}

variable "analysts_group_id" {
  type        = string
  description = "Entra ID group object id for analysts (workspace Viewer)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
