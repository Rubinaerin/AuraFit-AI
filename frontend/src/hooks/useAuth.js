import React, { createContext, useContext, useState, useEffect } from "react";
import api from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    // Hydrate the user state from localStorage on initial load to persist the session
    const storedUser = localStorage.getItem("fitcore_user");
    return storedUser ? JSON.parse(storedUser) : null;
  });
  const [loading, setLoading] = useState(true);

  // Sync user state changes with localStorage
  const updateActiveUser = (userData) => {
    if (userData) {
      localStorage.setItem("fitcore_user", JSON.stringify(userData));
    } else {
      localStorage.removeItem("fitcore_user");
      localStorage.removeItem("fitcore_token");
    }
    setUser(userData);
  };

  // Automatically verify session validity and fetch fresh data on app startup
  useEffect(() => {
    const verifySession = async () => {
      const token = localStorage.getItem("fitcore_token");
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        // Fetch the fresh authenticated user profile directly from the database
        const { data } = await api.get("/users/me");
        updateActiveUser(data);
      } catch (err) {
        console.error("Session verification failed:", err);
        // Clean up stale session credentials if verification fails
        updateActiveUser(null);
      } finally {
        setLoading(false);
      }
    };

    verifySession();
  }, []);

  const logout = () => {
    updateActiveUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, setUser: updateActiveUser, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}