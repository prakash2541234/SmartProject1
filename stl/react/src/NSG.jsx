import React, { useState } from "react";

export default function NSG() {
  const [basic, setBasic] = useState({
    subscription: "",
    resourceGroup: "",
    nsgName: "",
    region: "",
  });

  const [rule, setRule] = useState({
    source: "Any",
    sourcePort: "*",
    destination: "Any",
    service: "Custom",
    destinationPort: "",
    protocol: "TCP",
    action: "Allow",
    priority: "",
    name: "",
  });

  const [rules, setRules] = useState([]);

  const handleBasicChange = (e) => {
    setBasic({ ...basic, [e.target.name]: e.target.value });
  };

  const handleRuleChange = (e) => {
    const { name, value } = e.target;

    let updatedRule = { ...rule, [name]: value };

    const servicePorts = {
      HTTP: "80",
      HTTPS: "443",
      SSH: "22",
      RDP: "3389",
      MySQL: "3306",
    };

    if (name === "service") {
      updatedRule.destinationPort = servicePorts[value] || "";
    }

    setRule(updatedRule);
  };

  const addRule = () => {
    setRules([...rules, rule]);
    setRule({
      source: "Any",
      sourcePort: "*",
      destination: "Any",
      service: "Custom",
      destinationPort: "",
      protocol: "TCP",
      action: "Allow",
      priority: "",
      name: "",
    });
  };

  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>
      <h2>Create Network Security Group</h2>

      {/* Basic Details */}
      <div>
        <h3>Basic Details</h3>
        <input name="subscription" placeholder="Subscription" onChange={handleBasicChange} /> 
        <input name="resourceGroup" placeholder="Resource Group" onChange={handleBasicChange} />
        <input name="nsgName" placeholder="NSG Name" onChange={handleBasicChange} />
        <input name="region" placeholder="Region" onChange={handleBasicChange} />
      </div>

      {/* Inbound Rule */}
      <div style={{ marginTop: "20px" }}>
        <h3>Add Inbound Rule</h3>

        <label>Source : </label>
        <select name="source" value={rule.source} onChange={handleRuleChange}>
          <option>Any</option>
          <option>IP Addresses</option>
          <option>My IP Address</option>
          <option>Service Tag</option>
          <option>Application Security Group</option>
        </select> <br />

        <label>Source Port  :  </label>
        <input
          name="sourcePort"
          placeholder="Source Port"
          value={rule.sourcePort}
          onChange={handleRuleChange}
        /> <br />
        
        <label>Destination : </label>
        <select name="destination" value={rule.destination} onChange={handleRuleChange}>
          <option>Any</option>
          <option>IP Addresses</option>
          <option>Virtual Network</option>
          <option>Application Security Group</option>
        </select> <br />

        <label>Service : </label>
        <select name="service" value={rule.service} onChange={handleRuleChange}>
          <option>Custom</option>
          <option>HTTP</option>
          <option>HTTPS</option>
          <option>SSH</option>
          <option>RDP</option>
          <option>MySQL</option>
        </select> <br />

        <label>Destination port : </label>
        <input
          name="destinationPort"
          placeholder="Destination Port"
          value={rule.destinationPort}
          onChange={handleRuleChange}
        /> <br />

        <label>Protocol : </label>
        <select name="protocol" value={rule.protocol} onChange={handleRuleChange}>
          <option>Any</option>
          <option>TCP</option>
          <option>UDP</option>
          <option>ICMPv4</option>
          <option>ICMPv6</option>
        </select> <br />

        <label>Action : </label>
        <select name="action" value={rule.action} onChange={handleRuleChange}>
          <option>Allow</option>
          <option>Deny</option>
        </select> <br />

        <label>Priority : </label>
        <input
          name="priority"
          placeholder="Priority (100, 200...)"
          value={rule.priority}
          onChange={handleRuleChange}
        /> <br />

        <label>Rule Name : </label>
        <input
          name="name"
          placeholder="Rule Name"
          value={rule.name}
          onChange={handleRuleChange}
        /> <br />

        <button onClick={addRule}>Add Rule</button>
      </div>

      {/* Rules List */}
      <div style={{ marginTop: "20px" }}>
        <h3>Rules</h3>
        <ul>
          {rules.map((r, index) => (
            <li key={index}>
              {r.name} - {r.protocol} - {r.destinationPort} - {r.action}
            </li>
          ))}
        </ul>
      </div>

      <button style={{ marginTop: "20px" }}>Create NSG</button>
    </div>
  );
}
