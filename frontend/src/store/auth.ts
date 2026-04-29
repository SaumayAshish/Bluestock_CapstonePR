import { create } from "zustand";

type Role = "admin" | "portal";

type AuthState = {
  adminToken: string;
  portalToken: string;
  setToken: (role: Role, token: string) => void;
  logout: (role: Role) => void;
};

const read = (key: string) => localStorage.getItem(key) || "";

export const useAuthStore = create<AuthState>((set) => ({
  adminToken: read("bluestock.adminToken"),
  portalToken: read("bluestock.portalToken"),
  setToken: (role, token) => {
    const key = role === "admin" ? "bluestock.adminToken" : "bluestock.portalToken";
    localStorage.setItem(key, token);
    set(role === "admin" ? { adminToken: token } : { portalToken: token });
  },
  logout: (role) => {
    const key = role === "admin" ? "bluestock.adminToken" : "bluestock.portalToken";
    localStorage.removeItem(key);
    set(role === "admin" ? { adminToken: "" } : { portalToken: "" });
  }
}));
