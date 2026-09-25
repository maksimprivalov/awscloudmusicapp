import { Component, OnInit } from '@angular/core';
import { ContentService } from '../../core/content.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-content-list',
  templateUrl: './content-list.component.html',
  styleUrls: ['./content-list.component.css'],
  standalone: false
})
export class ContentListComponent implements OnInit {
  items: any[] = [];
  loading = false;

  constructor(private api: ContentService, private router: Router) {}

  ngOnInit(): void {
    this.loading = true;
    this.api.listContent().subscribe({
      next: (res) => { this.items = res; this.loading = false; },
      error: () => { this.loading = false; }
    });
  }

  open(id: string) {
  this.router.navigate(['/content', id]);
}

}
