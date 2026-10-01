import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.jsx";
import { AppSettingsProvider } from "./context/AppSettingsContext.jsx";
import { DataProvider } from "./context/DataContext.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AppSettingsProvider>
        <DataProvider>
          <App />
        </DataProvider>
      </AppSettingsProvider>
    </BrowserRouter>
  </StrictMode>
);
