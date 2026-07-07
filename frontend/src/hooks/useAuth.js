import React, { createContext, useContext, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Test aşamasında jüriye profil bilgilerini göstermek için varsayılan bir kullanıcı objesi kilitliyoruz
  const [user] = useState({
    id: 1,
    full_name: "Rubina Erin",
    email: "rubina@example.com",
    primary_goal: "muscle_gain",
    fitness_level: "intermediate",
    height_cm: 175,
    current_weight_kg: 70,
    health_conditions: []
  });

  return (
    <AuthContext.Provider value={{ user, loading: false }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}