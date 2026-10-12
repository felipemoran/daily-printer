// A failure of the server, not of the sender's data.
export const serverFault = (message: string): Error => Object.assign(new Error(message), { name: 'ServerFault' })
