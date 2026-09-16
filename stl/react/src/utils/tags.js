export const parseTagsText = (text) => {
  const tags = {};
  const invalid = [];
  const lines = String(text || "").split("\n");

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      return;
    }

    const delimiterIndex = trimmed.includes("=") ? trimmed.indexOf("=") : trimmed.indexOf(":");
    if (delimiterIndex <= 0) {
      invalid.push(`Line ${index + 1}: use key=value format.`);
      return;
    }

    const key = trimmed.slice(0, delimiterIndex).trim();
    const value = trimmed.slice(delimiterIndex + 1).trim();
    if (!key) {
      invalid.push(`Line ${index + 1}: key is required.`);
      return;
    }

    tags[key] = value;
  });

  return { tags, invalid };
};
