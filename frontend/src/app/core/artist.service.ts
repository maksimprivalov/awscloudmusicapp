import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface ArtistCreateRequest {
  name: string;
  bio: string;
  genres: string[];
}

export interface ArtistCreateResponse {
  message: string;
  artistId: string;
}

export interface ArtistDto {
  artistId: string;
  name: string;
  bio?: string;
  genres?: string[];
  createdAt?: string;
  updatedAt?: string;
}

export interface UpdateArtistPayload {
  artistId: string;
  name?: string;
  bio?: string;
  genres?: string[];
}

@Injectable({ providedIn: 'root' })
export class ArtistService {
  private base = environment.apiBase;

  constructor(private http: HttpClient) {}

  create(payload: ArtistCreateRequest): Observable<ArtistCreateResponse> {
    return this.http.post<ArtistCreateResponse>(`${this.base}/admin/artist`, payload);
  }

  getArtists() {
    return this.http.get<ArtistDto[]>(`${this.base}/artists`);
  }

  updateArtist(payload: UpdateArtistPayload) {
    return this.http.post<{message:string}>(`${this.base}/admin/artist/update`, payload);
  }

  deleteArtist(artistId: string) {
    return this.http.delete<{message:string}>(`${this.base}/admin/artist/${encodeURIComponent(artistId)}`);
  }
}
