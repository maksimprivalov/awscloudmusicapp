import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';
import { tap } from 'rxjs/operators';

export interface RegisterDto {
  first_name: string;
  last_name: string;
  birthdate: string; // YYYY-MM-DD
  email: string;
  password: string;
}
export interface LoginDto {
  email: string;
  password: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private tokenKey = 'jwt';
  constructor(private http: HttpClient) {}

  register(payload: RegisterDto) {
    return this.http.post(`${environment.apiBase}/auth/register`, payload);
  }

  login(payload: LoginDto) {
    return this.http
      .post<{ idToken: string }>(`${environment.apiBase}/auth/login`, payload)
      .pipe(tap(res => localStorage.setItem(this.tokenKey, res.idToken)));
  }

  isAuthenticated(): boolean { return !!localStorage.getItem(this.tokenKey); }
  getToken(): string | null { return localStorage.getItem(this.tokenKey); }
  logout() { localStorage.removeItem(this.tokenKey); }
}
