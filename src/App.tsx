import CameraManager from "./features/cctv/CameraManager";

function App() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-start",
        alignItems: "center",
        minHeight: "100vh",
        backgroundColor: "#050505",
        color: "#fff",
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
        padding: "40px 20px",
        overflowY: "auto",
        boxSizing: "border-box",
      }}
    >
      <div style={{ width: "100%", maxWidth: "1600px" }}>
        <CameraManager />
      </div>
    </div>
  );
}

export default App;
