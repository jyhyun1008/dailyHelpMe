self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  let data = {title:'날도와줘',body:'새 메시지가 도착했어요.'};
  try { if(event.data) data = {...data,...event.data.json()}; } catch (_) {}
  event.waitUntil(self.registration.showNotification(data.title, {
    body:data.body,icon:'/icon.png',badge:'/icon.png',data:{url:'/'},
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients => {
    const existing = clients.find(client => new URL(client.url).origin === self.location.origin);
    if(existing) { await existing.focus(); existing.postMessage({type:'open-chat'}); return; }
    return self.clients.openWindow('/?tab=chat');
  }));
});
