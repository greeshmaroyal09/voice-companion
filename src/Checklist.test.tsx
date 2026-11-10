import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Checklist, type Preparation } from './Checklist';

describe('preparation checklist', () => {
  it('hides unsupported guidance and renders uncertainty, sources and synthetic samples', () => {
    expect(renderToStaticMarkup(<Checklist disabled={false} onAsk={() => {}} />)).toBe('');
    const preparation: Preparation = { answers: {}, pending: '', focus: 'visit', coverage: 'SBI only', notice: 'No guarantee', checklist: [{id:'visit',title:'కాపీలు',kind:'branch_confirmation',text:'Counts unverified',status:'unverified',conditions:'Branch route',exceptions:'No count asserted',category:'Adult',branch_confirmation:true,sources:[{title:'Official source',url:'https://sbi.bank.in/',checked_on:'2026-11-08',published_or_updated:null,effective_date:null}]}] };
    const html = renderToStaticMarkup(<Checklist preparation={preparation} disabled={true} onAsk={() => {}} />);
    expect(html).toContain('ఇంకా ధృవీకరించలేదు');
    expect(html).toContain('SAMPLE — NOT A VALID DOCUMENT');
    expect(html).toContain('https://sbi.bank.in/');
    expect(html).toContain('2026-11-08');
    expect(html).toContain('disabled');
    expect(html).not.toContain('type="file"');
  });
});
