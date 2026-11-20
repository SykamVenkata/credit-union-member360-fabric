output "workspace_id" {
  value = fabric_workspace.this.id
}

output "lakehouse_id" {
  value = fabric_lakehouse.member360.id
}

output "warehouse_id" {
  value = fabric_warehouse.member360.id
}
