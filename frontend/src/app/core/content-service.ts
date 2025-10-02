// src/app/core/content.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams, HttpHeaders } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ContentService {
  subscribeToContent(targetType: string, targetId: string) {
    return this.http.post(`${this.base}/user/subscribe`, {
      targetType,
      targetId
    });
  }

  subscribeToTarget(targetType: 'TRACK'|'ALBUM'|'ARTIST', targetId: string) {
    return this.http.post(`${this.base}/user/subscribe`, { targetType, targetId });
  }

  private base = environment.apiBase;

  constructor(private http: HttpClient) {}

  // ADMIN
  getUploadUrl(fileName: string, contentType: string) {
    return this.http.post<{ contentId: string; s3Key: string; uploadUrl: string }>(
      `${this.base}/admin/content/upload-url`,
      { fileName, contentType }
    );
  }

  createContent(payload: {
    contentId: string; s3Key: string; name: string;
    genres?: string[]; artists?: string[]; albumId?: string | null; trackNo?: number;
  }) {
    return this.http.post(`${this.base}/admin/content`, payload);
  }

  // PUBLIC
  listContent() {
    return this.http.get<any[]>(`${this.base}/content`);
  }

  getContent(id: string) {
    return this.http.get<any>(`${this.base}/content/${id}`);
  }
  discover(genre: string, type: 'ALBUM'|'ARTIST'|'' = '', limit = 12, lastKey?: string) {
    let params = new HttpParams().set('genre', genre).set('limit', limit);
    if (type) params = params.set('type', type);
    if (lastKey) params = params.set('lastKey', lastKey);
    return this.http.get<{ items: any[]; nextKey?: string }>(`${this.base}/discover`, { params });
  }

  // upload file to presigned URL (PUT directly to S3)
  async uploadToS3Presigned(url: string, file: File, contentType: string) {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body: file
    });
    if (!res.ok) throw new Error(`S3 upload failed: ${res.status}`);
    return true;
  }
}
