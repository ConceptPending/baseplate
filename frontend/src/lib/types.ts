export interface Item {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
  updated_at: string;
}
