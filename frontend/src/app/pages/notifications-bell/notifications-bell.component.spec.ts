import { ComponentFixture, TestBed } from '@angular/core/testing';

import { NotificationsBellComponent } from './notifications-bell.component';

describe('NotificationsBellComponent', () => {
  let component: NotificationsBellComponent;
  let fixture: ComponentFixture<NotificationsBellComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [NotificationsBellComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(NotificationsBellComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
