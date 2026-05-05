import React, { useState, useEffect } from "react";

const CCTVConnection = () => {
  const [backendUrl, setBackendUrl] = useState("http://localhost:8086");
  const [status, setStatus] = useState<"connected" | "disconnected" | "idle">("idle");

  useEffect(() => {
    const savedUrl = localStorage.getItem("ceova_backend_url");
    if (savedUrl) {
      setBackendUrl(savedUrl);
    }
  }, []);

  const testConnection = async () => {
    try {
      const response = await fetch(`${backendUrl}/status`);
      if (response.ok) {
        setStatus("connected");
      } else {
        setStatus("disconnected");
      }
    } catch (error) {
      setStatus("disconnected");
    }
  };

  const saveConnection = () => {
    localStorage.setItem("ceova_backend_url", backendUrl);
    alert("Connection URL saved!");
  };

  const containerStyle: React.CSSProperties = {
    background: "rgba(255, 255, 255, 0.03)",
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    padding: "32px",
    borderRadius: "24px",
    maxWidth: "400px",
    width: "100%",
    boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
    color: "#fff",
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    marginTop: "20px",
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "12px 16px",
    borderRadius: "12px",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    backgroundColor: "rgba(0, 0, 0, 0.2)",
    color: "#fff",
    marginBottom: "20px",
    fontSize: "14px",
    boxSizing: "border-box",
  };

  const buttonStyle = (variant: 'primary' | 'secondary'): React.CSSProperties => ({
    width: "100%",
    padding: "14px 20px",
    borderRadius: "12px",
    border: "none",
    fontWeight: "600",
    fontSize: "15px",
    cursor: "pointer",
    backgroundColor: variant === 'primary' ? "#3b82f6" : "rgba(255, 255, 255, 0.05)",
    color: "#fff",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    marginBottom: variant === 'primary' ? "12px" : "0",
    boxShadow: variant === 'primary' ? "0 4px 12px rgba(59, 130, 246, 0.3)" : "none",
  });

  const statusStyle: React.CSSProperties = {
    fontSize: "14px",
    fontWeight: "600",
    textAlign: "center",
    marginBottom: "20px",
    color: status === "connected" ? "#10b981" : status === "disconnected" ? "#ef4444" : "rgba(255, 255, 255, 0.4)",
  };

  return (
    <div style={containerStyle}>
      <h3 style={{ margin: "0 0 8px 0", fontSize: "20px" }}>Connection Settings</h3>
      <p style={{ color: "rgba(255, 255, 255, 0.5)", marginBottom: "24px", fontSize: "14px" }}>
        Configure your CCTV AI backend endpoint
      </p>

      <div style={{ marginBottom: "8px", fontSize: "12px", color: "rgba(255, 255, 255, 0.4)", fontWeight: "600" }}>
        BACKEND URL
      </div>
      <input
        type="text"
        value={backendUrl}
        onChange={(e) => setBackendUrl(e.target.value)}
        placeholder="http://localhost:8086"
        style={inputStyle}
      />

      <div style={statusStyle}>
        Status: {status === "connected" ? "Connected" : status === "disconnected" ? "Disconnected" : "Idle"}
      </div>

      <button onClick={testConnection} style={buttonStyle('primary')}>
        Test Connection
      </button>

      <button onClick={saveConnection} style={buttonStyle('secondary')}>
        Save Connection
      </button>
    </div>
  );
};

export default CCTVConnection;
