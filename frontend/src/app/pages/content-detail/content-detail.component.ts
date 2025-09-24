// src/app/pages/content-detail/content-detail.component.ts
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ContentService } from '../../core/content-service';

@Component({
  selector: 'app-content-detail',
  templateUrl: './content-detail.component.html',
  standalone: false
})
export class ContentDetailComponent implements OnInit {
  item: any; loading = false;

  constructor(private route: ActivatedRoute, private api: ContentService) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.loading = true;
    this.api.getContent(id).subscribe({
      next: r => { this.item = r; this.loading = false; },
      error: _ => { this.loading = false; }
    });
  }
}
