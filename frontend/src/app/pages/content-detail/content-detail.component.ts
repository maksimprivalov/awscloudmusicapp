import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ContentService } from '../../core/content-service';

@Component({
  selector: 'app-content-detail',
  templateUrl: './content-detail.component.html',
  standalone: false
})
export class ContentDetailComponent implements OnInit {
  item: any; 
  loading = false;
  subStatus?: string;

  constructor(private route: ActivatedRoute, private api: ContentService) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.loading = true;
    this.api.getContent(id).subscribe({
      next: r => { this.item = r; this.loading = false; },
      error: _ => { this.loading = false; }
    });
  }

  subscribe() {
    if (!this.item?.contentId) return;
    this.subStatus = "⏳ Pretplaćujem se...";

    this.api.subscribeToContent("TRACK", this.item.contentId).subscribe({
      next: () => this.subStatus = "✅ Uspešno pretplaćen!",
      error: (err) => this.subStatus = `❌ Greška: ${err.message || err}`
    });
  }
}
