import React from "react";
import { useNavigate } from "react-router-dom";
import "./ApiButtons.css";

export default function ApiButtons() {
  const navigate = useNavigate();
  
  const buttons = [
    { id: 1, name: "Create User", path: "/create-user" },
    { id: 2, name: "Create Group", path: "/create-group" },
    { id: 3, name: "Create Resource Group", path: "/create-resource-group" },
    { id: 5, name: "Create V.Net", path: "/create-vnet" },
    { id: 6, name: "Key Vault", path: "/create-key-vault" },
    { id:12, name: "Key Vault1", path: "/create-key-vault1" },
    { id: 7, name: "Service Principal", path: "/create-service-principal" },
    { id: 8, name: "Backup", path: "/create-backup" },
    { id: 9, name: "Virtual Machine", path: "/vm" },
    { id: 11, name: "NSG", path: "/nsg"},
    { id :13, name: "Decommission Subscription", path: "/decommission-subscription"},
    { id: 10, name: "Template2", path: "/Template2"},
    { id: 14, name: "Assign Roles with Scope", path: "/assign-roles-with-scope"},
    { id: 15, name: "View Role Assignments", path: "/view-role-assignments"},
    { id : 16, name: "Service Principals", path: "/service-principals"},
    { id : 17, name: "Delete User", path: "/delete-user"},
    { id : 18, name: "Dashboard API", path: "/dashboard-api"},
    { id: 19, name: "Tracker", path: "/tracker" },
  ];

  const handleApiClick = (button) => {
    if (button.path) {
      navigate(button.path);
    } else {
      console.log(`${button.name} clicked - API call will be integrated here`);
    }
  };

  return (
    
  <div className="api-buttons-page">
    <h2 className="api-buttons-title">API Actions</h2>
    <div className="api-buttons-container">
        {buttons.map((button) => (
          <button
            key={button.id}
            className="api-button"
            onClick={() => handleApiClick(button)}
          >
            {button.name}
          </button>
        ))}
      </div>
        <div className="api-button-2">
          <button
            className="automation-btn"
            onClick={() => navigate("/Template")}
          >
            Template
          </button>

          <button
            className="automation-btn"
            onClick={() => navigate("/Subscription-auto")}
          >
            Status Checker
          </button>
        </div>
    </div>
  );
}
