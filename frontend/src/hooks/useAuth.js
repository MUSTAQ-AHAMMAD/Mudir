// useAuth.js — re-export of the Auth context hook for convenient imports.
import { useAuthContext } from '../context/AuthContext';

export function useAuth() {
  return useAuthContext();
}

export default useAuth;
