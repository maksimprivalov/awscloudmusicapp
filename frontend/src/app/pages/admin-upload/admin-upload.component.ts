import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import { ContentService } from '../../core/content-service';

@Component({
  selector: 'app-admin-upload',
  templateUrl: './admin-upload.component.html',
  standalone: false
})
export class AdminUploadComponent {
 form;

  uploading = false;
  status?: string;
  createdId?: string;

  constructor(private fb: FormBuilder, private content: ContentService) {
    this.form = this.fb.group({
      name: ['', Validators.required],
      genres: ['rock'],
      artists: [''],
      albumId: [''],
      trackNo: [1],
      file: [null as File | null],
    });
  }



  async submit() {
    if (!this.form.valid) return;
    const file = this.form.value.file as File | null;
    if (!file) { this.status = 'Izaberite fajl'; return; }

    try {
      this.uploading = true; this.status = 'Tražim upload URL...';
      const contentType = file.type || 'application/octet-stream';
      const up = await this.content.getUploadUrl(file.name, contentType).toPromise();

      this.status = 'Šaljem fajl u S3...';
      await this.content.uploadToS3Presigned(up!.uploadUrl, file, contentType);

      this.status = 'Upisujem metapodatke...';
      const genres = (this.form.value.genres || '').toString().split(',').map(s => s.trim()).filter(Boolean);
      const artists = (this.form.value.artists || '').toString().split(',').map(s => s.trim()).filter(Boolean);

      await this.content.createContent({
        contentId: up!.contentId,
        s3Key: up!.s3Key,
        name: this.form.value.name!,
        genres,
        artists,
        albumId: this.form.value.albumId || null,
        trackNo: Number(this.form.value.trackNo || 1),
      }).toPromise();

      this.createdId = up!.contentId;
      this.status = 'Gotovo!';
    } catch (e:any) {
      this.status = `Greška: ${e.message || e}`;
    } finally {
      this.uploading = false;
    }
  }

  onFileChange(ev: any) {
    const f: File = ev.target?.files?.[0];
    this.form.patchValue({ file: f });
  }
}
