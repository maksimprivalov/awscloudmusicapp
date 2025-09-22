import { TestBed } from '@angular/core/testing';

import { DiscoverService } from './discover.service';

describe('Discover', () => {
  let service: DiscoverService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DiscoverService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
