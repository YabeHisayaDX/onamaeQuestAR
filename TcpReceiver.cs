using System.Collections;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

public class TcpReceiver : MonoBehaviour
{
    private int port = 6002;
    private int width = 640;
    private int height = 360;

    private TcpListener server;
    private TcpClient client;
    private NetworkStream stream;
    private Thread receiveThread;
    
    private Texture2D tex;
    private byte[] pendingData = null;
    private object dataLock = new object();
    private bool isRunning = true;

    void Start()
    {
        // 起動確認：水色
        tex = new Texture2D(width, height, TextureFormat.RGB24, false);
        for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) tex.SetPixel(x, y, Color.cyan);
        tex.Apply();

        Renderer rend = GetComponent<Renderer>();
        if (rend != null) {
            rend.material.mainTexture = tex;
            //rend.material.shader = Shader.Find("Unlit/Texture");
        }

        StartServer();
    }

    void StartServer()
    {
        if (receiveThread != null) receiveThread.Abort();
        receiveThread = new Thread(new ThreadStart(ListenForClients));
        receiveThread.IsBackground = true;
        receiveThread.Start();
    }

    void Update()
    {
        byte[] dataToProcess = null;
        lock (dataLock) {
            if (pendingData != null) {
                dataToProcess = pendingData;
                pendingData = null;
            }
        }

        if (dataToProcess != null)
        {
            // ここで落ちないようにtry-catch
            try { tex.LoadImage(dataToProcess); } catch {}
        }
    }

    void ListenForClients()
    {
        try { server = new TcpListener(IPAddress.Any, port); server.Start(); } catch {}

        while (isRunning)
        {
            try {
                if (client == null) {
                    if (server.Pending()) {
                        client = server.AcceptTcpClient();
                        stream = client.GetStream();
                        Debug.Log("🚀 接続しました");
                    } else {
                        Thread.Sleep(100); 
                        continue;
                    }
                }

                // データ待ち
                if (client.Available < 8) {
                    // ★重要：もし切断されていたらここで検知してループを抜ける
                    if (!IsConnected(client)) {
                        ResetConnection();
                        continue;
                    }
                    Thread.Sleep(5);
                    continue;
                }

                // 1. 合言葉 "IMG!" チェック
                // ★修正点：読み込みに失敗(-1)したら、即座に切断する（無限ループ回避）
                int b1 = stream.ReadByte(); if (b1 == -1 || b1 != 'I') { ResetConnection(); continue; }
                int b2 = stream.ReadByte(); if (b2 == -1 || b2 != 'M') { ResetConnection(); continue; }
                int b3 = stream.ReadByte(); if (b3 == -1 || b3 != 'G') { ResetConnection(); continue; }
                int b4 = stream.ReadByte(); if (b4 == -1 || b4 != '!') { ResetConnection(); continue; }

                // 2. サイズ受信
                byte[] sizeBytes = new byte[4];
                int bytesRead = stream.Read(sizeBytes, 0, 4);
                if (bytesRead < 4) { ResetConnection(); continue; }

                if (System.BitConverter.IsLittleEndian) System.Array.Reverse(sizeBytes);
                int dataSize = System.BitConverter.ToInt32(sizeBytes, 0);

                if (dataSize <= 0 || dataSize > 200000) { ResetConnection(); continue; }

                // 本体待ち
                int timeout = 0;
                while (client.Available < dataSize && timeout < 100) {
                    Thread.Sleep(1);
                    timeout++;
                }
                if (client.Available < dataSize) { ResetConnection(); continue; }

                // 3. 画像データ読み込み
                byte[] imageBytes = new byte[dataSize];
                int totalRead = 0;
                int readError = 0;
                while (totalRead < dataSize) {
                    int read = stream.Read(imageBytes, totalRead, dataSize - totalRead);
                    if (read == 0) { readError = 1; break; }
                    totalRead += read;
                }
                if (readError == 1) { ResetConnection(); continue; }

                lock (dataLock) {
                    pendingData = imageBytes;
                }
            }
            catch {
                ResetConnection();
            }
        }
    }

    // 接続状態確認用
    bool IsConnected(TcpClient c) {
        try {
            if (c != null && c.Client != null && c.Client.Connected) {
                if (c.Client.Poll(0, SelectMode.SelectRead)) {
                    return !(c.Client.Receive(new byte[1], SocketFlags.Peek) == 0);
                }
                return true;
            } else { return false; }
        } catch { return false; }
    }

    void ResetConnection() {
        if (client != null) client.Close();
        client = null;
        Debug.Log("🔌 リセット（再接続待機）");
        Thread.Sleep(100); // 連続リセット防止の休憩
    }

    void OnApplicationQuit()
    {
        isRunning = false;
        if (server != null) server.Stop();
        if (receiveThread != null) receiveThread.Abort();
    }
}