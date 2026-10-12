import T from '.'

// design-system/components/TicketTemplate/preview.html, ported as is.
export default function TicketExample() {
  return (
    <T.Paper print>
      <T.HeaderBar left="TICKET UPDATE" right="14:08" />
      <div className="display-xl" style={{ marginTop: 20, letterSpacing: -1 }}>OPS-2481</div>
      <div style={{ fontSize: 21, fontWeight: 700, lineHeight: '26px', marginTop: 12 }}>
        Payment webhook retries exceed limit on EU cluster
      </div>
      <div style={{ height: 28 }} />
      <T.Transition from="IN REVIEW" to="RESOLVED" />
      <div style={{ height: 28 }} />
      <T.Leaders rows={[['Assignee', 'M. Okafor'], ['Priority', 'HIGH'], ['Reporter', 'S. Lindqvist'], ['Time spent', '3h 20m'], ['Opened', '2d ago']]} />
      <T.Rule weight="rule" style={{ margin: '28px 0 8px' }} />
      <T.Quote by="M. Okafor">Raised retry cap to 8 and added jitter. Backlog drained in 11 min. Monitoring overnight.</T.Quote>
      <T.Rule weight="rule" style={{ margin: '28px 0 20px' }} />
      <T.QRSlot lines={['Scan to open ticket', '3 watchers notified', 'Next: auto-close in 48h']} />
    </T.Paper>
  )
}
