import React, { useEffect, useState } from "react";

/* UTIL #1: Clean project name into safe VNet-friendly string */
function cleanProjectName(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

  /* UTIL #2: Generate VNet Name */
function buildVNetName(projectName) {
  const cleaned = cleanProjectName(projectName);
  return `${cleaned}-vnet`.slice(0, 120);
}

/* UTIL #3: Generate VNet Address Space using deterministic hash*/
function buildVNetAddress(projectName) {
  const cleaned = cleanProjectName(projectName);

  // Simple deterministic hash → 0-255
  let hash = 0;
  for (let i = 0; i < cleaned.length; i++) {
    hash = (hash + cleaned.charCodeAt(i)) % 255;
  }

  // /16 block 10.x.0.0/16
  return `10.${hash}.0.0/16`;
}

function generateSubnets(vnetCidr, count) {
  const base = vnetCidr.split("/")[0]; // "10.x.0.0"
  const [a, b] = base.split(".");

  const subnets = [];

  for (let i = 1; i <= count; i++) {
    subnets.push({
      subnetName: `subnet-${i}`,
      addressPrefix: `${a}.${b}.${i}.0/24`,
    });
  }
  return subnets;
}

export default function VNetBuilder({ projectName, subnetCount, onGenerated }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!projectName) return;

    const vnetName = buildVNetName(projectName);
    const vnetAddress = buildVNetAddress(projectName);
    const subnets = generateSubnets(vnetAddress, subnetCount);

    const result = {
      projectName,
      vnetName,
      vnetAddress,
      subnets,
    };

    setData(result);

    // Auto‑return result to subscription-auto.jsx
    if (onGenerated) {
      onGenerated(result);
    }
  }, [projectName, subnetCount]);

  // For debugging on screen (optional)
  return (
    <div style={{ padding: "12px", background: "#f5f5f5", borderRadius: "8px" }}>
      {data ? (
        <>
          <h3>Generated VNet Configuration</h3>
          <p><b>Project:</b> {data.projectName}</p>
          <p><b>VNet Name:</b> {data.vnetName}</p>
          <p><b>VNet Address:</b> {data.vnetAddress}</p>
          <h4>Subnets</h4>
          <ul>
            {data.subnets.map((s, i) => (
              <li key={i}>
                {s.subnetName} → {s.addressPrefix}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>Waiting for projectName...</p>
      )}
    </div>
  );
}