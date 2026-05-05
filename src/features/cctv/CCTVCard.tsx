import React from "react";
import { useCCTVStatus } from "./useCCTVStatus";
import { startCCTV, stopCCTV } from "../../services/cctvApi";

// Improved detection for Tauri v2
const isTauri = typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "TAURI_INTERNALS" in window || "__TAURI__" in window);

const CCTVCard = () => {
  const { connection, system } = useCCTVStatus();

  const cardStyle: React.CSSProperties = {
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
  };

  const buttonStyle = (disabled: boolean, variant: 'primary' | 'secondary'): React.CSSProperties => ({
    padding: "14px 20px",
    borderRadius: "12px",
    border: "none",
    fontWeight: "600",
    fontSize: "15px",
    cursor: disabled ? "not-allowed" : "pointer",
    backgroundColor: disabled 
      ? "rgba(255, 255, 255, 0.05)" 
      : variant === 'primary' ? "#3b82f6" : "#ef4444",
    color: disabled ? "rgba(255, 255, 255, 0.2)" : "white",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    flex: 1,
    boxShadow: disabled ? "none" : "0 4px 12px rgba(0, 0, 0, 0.2)",
  });

  if (!isTauri) {
    return (
      <div style={cardStyle}>
        <h2 style={{ margin: "0 0 8px 0", fontSize: "24px" }}>CCTV AI</h2>
        <p style={{ color: "rgba(255, 255, 255, 0.5)", marginBottom: "24px", fontSize: "15px" }}>Smart CCTV analytics powered by Ceova</p>
        <div style={{ 
          color: "#ff4d4d", 
          fontWeight: "600", 
          textAlign: "center", 
          padding: "16px", 
          background: "rgba(255, 77, 77, 0.08)", 
          borderRadius: "12px",
          border: "1px solid rgba(255, 77, 77, 0.2)"
        }}>
          Download Ceova Desktop App to use CCTV AI
        </div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <h2 style={{ margin: "0 0 8px 0", fontSize: "24px" }}>CCTV AI</h2>
      <p style={{ color: "rgba(255, 255, 255, 0.5)", marginBottom: "24px", fontSize: "15px" }}>Smart CCTV analytics powered by Ceova</p>

      <div style={{ background: "rgba(0, 0, 0, 0.2)", padding: "20px", borderRadius: "16px", marginBottom: "24px", border: "1px solid rgba(255, 255, 255, 0.05)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
          <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "14px" }}>Connection</span>
          <span style={{ color: connection === "online" ? "#10b981" : "#ef4444", fontWeight: "700", fontSize: "14px" }}>
            {connection === "online" ? "● ONLINE" : "● OFFLINE"}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "14px" }}>System</span>
          <span style={{ color: system === "running" ? "#3b82f6" : "#94a3b8", fontWeight: "700", fontSize: "14px" }}>
            {system === "running" ? "Running" : "Idle"}
          </span>
        </div>
      </div>

      {connection === "offline" && (
        <div style={{ 
          color: "#ff4d4d", 
          fontSize: "13px", 
          textAlign: "center", 
          marginBottom: "20px",
          padding: "12px",
          background: "rgba(255, 77, 77, 0.08)",
          borderRadius: "12px",
          border: "1px solid rgba(255, 77, 77, 0.1)"
        }}>
          CCTV backend not running. Please start the local AI system.
        </div>
      )}

      <div style={{ display: "flex", gap: "12px" }}>
        <button
          onClick={() => {
            const savedUrl = localStorage.getItem("ceova_selected_camera");
            if (!savedUrl) {
              alert("Please connect and select a camera first.");
              return;
            }
            startCCTV(savedUrl);
          }}
          disabled={connection === "offline" || system === "running"}
          style={buttonStyle(connection === "offline" || system === "running", 'primary')}
        >
          Start AI
        </button>
        <button
          onClick={() => stopCCTV()}
          disabled={connection === "offline" || system === "idle"}
          style={buttonStyle(connection === "offline" || system === "idle", 'secondary')}
        >
          Stop AI
        </button>
      </div>
    </div>
  );
};

export default CCTVCard;

