import React, { useState, useEffect } from "react";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

interface Camera {
  id: string;
  name: string;
  ip: string;
  username: string;
  rtsp_url: string;
}

const CameraManager = () => {
  const [cameras, setCameras] = useState<Record<string, Camera>>({});
  const [activeCameraId, setActiveCameraId] = useState<string | null>(null);
  const [cameraStatuses, setCameraStatuses] = useState<Record<string, {status: string, reason?: string}>>({});
  
  const [status, setStatus] = useState<"idle" | "error" | "loading">("loading");
  const [_loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [backendStatus, setBackendStatus] = useState<"ONLINE" | "OFFLINE">("OFFLINE");
  const [locationEnabled, setLocationEnabled] = useState(localStorage.getItem("ceova_location_enabled") === "true");
  const [location, setLocation] = useState<{lat: number, lon: number} | null>(null);
  const [updateStatus, setUpdateStatus] = useState<string>("");

  const apiBase = "http://localhost:8085";

  // --- AUTO UPDATER LOGIC ---
  const checkForUpdates = async (manual = false) => {
    try {
      setUpdateStatus("CHECKING...");
      const update = await check();
      if (update) {
        setUpdateStatus("NEW_VERSION_AVAILABLE");
        if (confirm(`New version available! Would you like to update?`)) {
          await update.downloadAndInstall();
          await relaunch();
        }
      } else {
        setUpdateStatus("LATEST");
        if (manual) alert("You are already on the latest version.");
      }
    } catch (err) {
      console.error(err);
      setUpdateStatus("CHECK_FAILED");
    }
  };

  // Backend Health Check
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${apiBase}/status`);
        if (res.ok) setBackendStatus("ONLINE");
        else setBackendStatus("OFFLINE");
      } catch { setBackendStatus("OFFLINE"); }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    checkForUpdates(false);
  }, []);

  // Location Services
  const toggleLocation = () => {
    const newState = !locationEnabled;
    setLocationEnabled(newState);
    localStorage.setItem("ceova_location_enabled", newState.toString());
    if (newState) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        (err) => console.warn("Location error:", err)
      );
    } else {
      setLocation(null);
    }
  };

  useEffect(() => {
    const fetchCameras = async () => {
      try {
        const sessionRes = await fetch(`${apiBase}/session-status`);
        if (!sessionRes.ok) throw new Error("Backend not reachable");
        const sessionData = await sessionRes.json();
        
        if (!sessionData.authenticated) {
            setStatus("error");
            setErrorMsg("Unauthorized. Please launch from Ceova Desktop.");
            setLoading(false);
            return;
        }

        const response = await fetch(`${apiBase}/cameras`);
        if (response.ok) {
          const data = await response.json();
          setCameras(data);
          
          const camIds = Object.keys(data);
          if (camIds.length > 0 && !activeCameraId) {
            setActiveCameraId(camIds[0]);
          }
          setStatus("idle");
        }
      } catch (err) {
        console.error("Failed to fetch cameras:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchCameras();
    const interval = setInterval(fetchCameras, 5000);
    return () => clearInterval(interval);
  }, [apiBase, activeCameraId]);

  useEffect(() => {
    const checkCameraStatuses = async () => {
      try {
        const response = await fetch(`${apiBase}/camera-statuses`);
        if (response.ok) {
          const data = await response.json();
          setCameraStatuses(data);
        }
      } catch (err) {
        console.error("Failed to fetch camera statuses:", err);
      }
    };

    checkCameraStatuses();
    const interval = setInterval(checkCameraStatuses, 3000);
    return () => clearInterval(interval);
  }, [apiBase]);



  const [viewMode, setViewMode] = useState<"single" | "grid">("grid");
  const [imgKeys, setImgKeys] = useState<Record<string, number>>({});

  const reloadStream = (cid: string) => {
    setImgKeys(prev => ({ ...prev, [cid]: (prev[cid] || 0) + 1 }));
  };

  const [currentTab, setCurrentTab] = useState<"LIVE" | "ALERTS" | "ANALYTICS">("LIVE");

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: "0 24px",
    height: "100%",
    display: "flex",
    alignItems: "center",
    cursor: "pointer",
    backgroundColor: active ? "#111" : "transparent",
    color: active ? "#fff" : "#666",
    borderBottom: active ? "2px solid #fff" : "none",
    fontSize: "11px",
    fontWeight: "bold",
    letterSpacing: "1px",
    transition: "all 0.2s"
  });

  if (status === "error" || status === "loading") {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "100vw", height: "100vh", background: "#000", color: "#fff", fontFamily: "monospace" }}>
        <div style={{ width: "400px", padding: "40px", border: "1px solid #222", background: "#050505", textAlign: "center" }}>
          <div style={{ marginBottom: "30px" }}>
            <div style={{ fontSize: "14px", fontWeight: "bold", letterSpacing: "2px" }}>CEOVA_SECURE</div>
            <div style={{ fontSize: "9px", color: "#444", marginTop: "4px" }}>ACCESS_TERMINAL_V4.0</div>
          </div>
          
          {status === "error" ? (
            <div style={{ color: "#f00", fontSize: "12px", textTransform: "uppercase" }}>// ERROR: {errorMsg}</div>
          ) : (
            <div style={{ color: "#fff", fontSize: "12px", textTransform: "uppercase" }}>CONNECTING TO BACKEND...</div>
          )}
        </div>
      </div>
    );
  }

  if (status === "idle") {
    const activeCamera = activeCameraId ? cameras[activeCameraId] : null;
    const cameraList = Object.values(cameras);

    return (
      <div style={{ display: "flex", flexDirection: "column", width: "100vw", height: "100vh", background: "#000", color: "#fff", fontFamily: "monospace" }}>
        {/* Top Navbar */}
        <div style={{ height: "50px", borderBottom: "1px solid #222", display: "flex", alignItems: "center", padding: "0 20px", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center" }}>
            <div style={{ fontSize: "12px", fontWeight: "bold", letterSpacing: "2px", marginRight: "60px" }}>CEOVA_SECURE</div>
            <div style={{ display: "flex", height: "100%", gap: "10px" }}>
              <div onClick={() => setCurrentTab("LIVE")} style={tabStyle(currentTab === "LIVE")}>LIVE_CCTV</div>
              <div onClick={() => setCurrentTab("ALERTS")} style={tabStyle(currentTab === "ALERTS")}>ALERTS</div>
              <div onClick={() => setCurrentTab("ANALYTICS")} style={tabStyle(currentTab === "ANALYTICS")}>ANALYTICS</div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "25px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <button 
                onClick={() => checkForUpdates(true)}
                style={{ padding: "6px 12px", border: "1px solid #444", background: "none", color: "#666", cursor: "pointer", fontSize: "9px", fontWeight: "bold" }}
              >
                CHECK_FOR_UPDATES {updateStatus ? `(${updateStatus})` : ""}
              </button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{ fontSize: "9px", color: "#666", letterSpacing: "1px" }}>SYSTEM_STATUS</div>
              <div style={{ fontSize: "10px", fontWeight: "bold", color: backendStatus === "ONLINE" ? "#0f0" : "#f00" }}>
                {backendStatus}
              </div>
            </div>
            <button 
              onClick={() => { localStorage.clear(); window.location.reload(); }}
              style={{ padding: "6px 12px", border: "1px solid #444", background: "none", color: "#888", cursor: "pointer", fontSize: "9px", fontWeight: "bold", letterSpacing: "1px" }}
            >
              TERMINATE_SESSION
            </button>
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          {currentTab === "LIVE" ? (
            <>
              {/* Sidebar */}
              <div style={{ width: "250px", borderRight: "1px solid #222", display: "flex", flexDirection: "column", padding: "20px" }}>
                <div style={{ fontSize: "10px", color: "#666", marginBottom: "20px", letterSpacing: "2px" }}>TERMINAL_DEVICES</div>
                
                {/* Location Toggle */}
                <div style={{ marginBottom: "20px", padding: "10px", border: "1px solid #222", borderRadius: "4px" }}>
                  <div style={{ fontSize: "8px", color: "#666", marginBottom: "8px" }}>IDENTIFICATION_SERVICES</div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "9px" }}>Location</span>
                    <button 
                      onClick={toggleLocation}
                      style={{ padding: "4px 8px", fontSize: "8px", backgroundColor: locationEnabled ? "#fff" : "#111", color: locationEnabled ? "#000" : "#fff", border: "1px solid #333", cursor: "pointer" }}
                    >
                      {locationEnabled ? "ENABLED" : "DISABLED"}
                    </button>
                  </div>
                  {location && (
                    <div style={{ fontSize: "8px", color: "#444", marginTop: "8px" }}>
                      LAT: {location.lat.toFixed(4)} | LON: {location.lon.toFixed(4)}
                    </div>
                  )}
                </div>
                
                <div style={{ display: "flex", gap: "2px", marginBottom: "20px" }}>
                  <button onClick={() => setViewMode("single")} style={{ flex: 1, padding: "8px", border: "1px solid #333", background: viewMode === "single" ? "#333" : "none", color: "#fff", fontSize: "10px", cursor: "pointer" }}>SINGLE</button>
                  <button onClick={() => setViewMode("grid")} style={{ flex: 1, padding: "8px", border: "1px solid #333", background: viewMode === "grid" ? "#333" : "none", color: "#fff", fontSize: "10px", cursor: "pointer" }}>GRID</button>
                </div>

                <div style={{ flexGrow: 1, overflowY: "auto" }}>
                  {cameraList.map(cam => (
                    <div key={cam.id} onClick={() => { setActiveCameraId(cam.id); setViewMode("single"); }} style={{ padding: "12px", border: "1px solid #222", marginBottom: "4px", background: activeCameraId === cam.id ? "#111" : "none", cursor: "pointer", fontSize: "12px", display: "flex", justifyContent: "space-between" }}>
                      <span>{cam.name}</span>
                      <span style={{ color: cameraStatuses[cam.id]?.status === "streaming" ? "#0f0" : "#f00" }}>●</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Main View */}
              <div style={{ flex: 1, padding: "20px", overflowY: "auto" }}>
                {viewMode === "single" && activeCamera ? (
                  <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
                    <div style={{ marginBottom: "12px", fontSize: "14px", borderBottom: "1px solid #222", paddingBottom: "10px" }}>
                      {activeCamera.name.toUpperCase()} // <span style={{ color: "#0f0" }}>LIVE_FEED</span>
                    </div>
                    <div style={{ flex: 1, background: "#050505", border: "1px solid #222", position: "relative", minHeight: "500px" }}>
                      <img key={`${activeCamera.id}-${imgKeys[activeCamera.id] || 0}`} src={`${apiBase}/stream/${activeCamera.id}?t=${imgKeys[activeCamera.id] || 0}`} alt="Feed" onError={() => reloadStream(activeCamera.id)} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", gap: "10px" }}>
                    {cameraList.map(cam => (
                      <div key={cam.id} style={{ background: "#050505", border: "1px solid #222", aspectRatio: "16/9", position: "relative" }}>
                        <img src={`${apiBase}/stream/${cam.id}?t=${imgKeys[cam.id] || 0}`} alt={cam.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        <div style={{ position: "absolute", top: "10px", left: "10px", background: "rgba(0,0,0,0.8)", padding: "4px 8px", fontSize: "10px", border: "1px solid #333" }}>{cam.name.toUpperCase()}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#333", letterSpacing: "10px", fontSize: "20px" }}>
              {currentTab}_MODULE_STANDBY
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "100vw", height: "100vh", background: "#000", color: "#333" }}>
      INITIALIZING_SECURE_LINK...
    </div>
  );
};

export default CameraManager;
