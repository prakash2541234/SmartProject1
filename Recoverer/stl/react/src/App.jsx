import React from "react";
import {BrowserRouter as Router, Route, Routes} from "react-router-dom";
import One from "./assets/open.jsx";
import ApiButtons from "./ApiButtons.jsx";
import CreateVNet from "./CreateVNet.jsx";
import CreateKeyVault from "./CreateKeyVault.jsx";
import CreateKeyVault1 from "./CreateKeyVault1.jsx";
import CreateServicePrincipal from "./CreateServicePrincipal.jsx";
import CreateUser from "./CreateUser.jsx";
import CreateGroup from "./CreateGroup.jsx";
import CreateResourceGroup from "./CreateResourceGroup.jsx";
import CreateBackup from "./CreateBackup.jsx";
import Vm from "./Vm.jsx";
import SubscriptionAuto from "./Subscription-auto.jsx";
import Template from "./Template.jsx";
import Template2 from "./Template2.jsx";
import Auto2 from "./Auto2.jsx";
import NewRect from "./NewRect.jsx";
import NSG from "./NSG.jsx";
import DecommissionSubscription from "./DecommissionSubscription.jsx";
import AssignRolesWithScope from "./Assing-Role.jsx";
import RoleAssignment from "./RoleAssignment.jsx";
import ServicePrincipals from "./LoadServicePrincipal.jsx";
import Dashboard from "./DashBoard.jsx";
import DeleteUser from "./DeleteUser.jsx";
import DashBoardAPI from "./DashBoardAPI.jsx";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<One />} />
        <Route path="/api" element={<ApiButtons />} />
        <Route path="/create-user" element={<CreateUser />} />
        <Route path="/create-group" element={<CreateGroup />} />
        <Route path="/create-resource-group" element={<CreateResourceGroup />} />
        <Route path="/create-backup" element={<CreateBackup />} />
        <Route path="/create-vnet" element={<CreateVNet />} />
        <Route path="/create-key-vault" element={<CreateKeyVault />} />
        <Route path="/create-service-principal" element={<CreateServicePrincipal />} />
        <Route path="/vm" element={<Vm />} />
        <Route path="/subscription-auto" element={<SubscriptionAuto />} />
        <Route path="/Template" element={<Template />} />
        <Route path="/Template2" element={<Template2 />} />
        <Route path="/auto2" element={<Auto2 />} />
        <Route path="/new-resource-group" element={<NewRect />} />
        <Route path="/nsg" element={<NSG />} />
        <Route path="/create-key-vault1" element={<CreateKeyVault1 />} />
        <Route path="/decommission-subscription" element={<DecommissionSubscription />} />
        <Route path="/assign-roles-with-scope" element={<AssignRolesWithScope />} />
        <Route path="/view-role-assignments" element={<RoleAssignment />} />
        <Route path="/service-principals" element={<ServicePrincipals />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/delete-user" element={<DeleteUser />} />
        <Route path="/dashboard-api" element={<DashBoardAPI />} />
      </Routes>
    </Router>
  );
}