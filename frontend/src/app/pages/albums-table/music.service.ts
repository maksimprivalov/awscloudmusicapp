import { Injectable } from '@angular/core';
import {HttpClient} from '@angular/common/http';
import { map } from 'rxjs/operators';
import { Observable} from 'rxjs';
import {TrackDto} from './albums-table.component';
import {environment} from '../../../environments/environment';

export interface UpdateAlbumPayload {
  albumId: string;
  name?: string;
  primaryGenre?: string;
  description?: string;
  artists?: string[];          // full replace
  addArtists?: string[];       // optional
  removeArtists?: string[];    // optional
  addContentIds?: string[];    // contentId traka za dodavanje
  removeContentIds?: string[]; // contentId traka za uklanjanje
  resequence?: boolean;        // 1..N
  order?: string[];            // precizan redosled (contentId)
}

@Injectable({ providedIn: 'root' })
export class MusicService {
  private base = environment.apiBase;

  constructor(private http: HttpClient) {}

  getAllTracks(): Observable<TrackDto[]> {
    return this.http.get<TrackDto[]>(`${this.base}/content`);
  }

  getTracksByAlbum(albumId: string): Observable<TrackDto[]> {
    return this.getAllTracks().pipe(
      map(list => list.filter(t => (t.albumId ?? '').trim() === albumId))
    );
  }

  getAlbumMeta(albumId: string) {
    return this.http.get<{ albumId: string; name?: string; primaryGenre?: string; genres?: string[]; artists?: string[]; description?: string }>(
      `${this.base}/album/${encodeURIComponent(albumId)}`
    );
  }

  deleteAlbum(albumId: string) {
    return this.http.delete<{message: string; tracksDeleted: number; albumDeleted?: boolean}>(
      `${this.base}/admin/album/${encodeURIComponent(albumId)}`
    );
  }

  updateAlbum(payload: UpdateAlbumPayload) {
    return this.http.post(`${this.base}/admin/album/update`, payload);
  }

  getArtist(artistId: string) {
    return this.http.get<{ artistId: string; name: string }>(
      `${this.base}/artist/${encodeURIComponent(artistId)}`
    );
  }

}
