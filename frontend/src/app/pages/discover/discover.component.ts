import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { DiscoverService } from '../../core/discover.service';

@Component({
  selector: 'app-discover',
  templateUrl: './discover.component.html',
  standalone: false

})
export class DiscoverComponent {
  form: FormGroup;
  items: any[] = [];
  total = 0;
  page = 0;
  size = 12;
  loading = false;

  constructor(private fb: FormBuilder, private svc: DiscoverService) {
    this.form = this.fb.group({
      genre: [''],
      artist: [''],
      album: [''],
    });
  }

  search(page = 0) {
    this.loading = true;
    this.page = page;
    this.svc
      .search({ ...(this.form.value as any), page: this.page, size: this.size })
      .subscribe({
        next: (res) => {
          this.items = res.items;
          this.total = res.total;
          this.loading = false;
        },
        error: () => (this.loading = false),
      });
  }
}
