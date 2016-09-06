#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import re
import sys
import json
import base64
import time
import atexit
import random
import grequests
from signal import SIGTERM
from datetime import datetime


class Daemon:
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        try:
            pid = os.fork()
            if pid > 0:
                #: exit first parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        os.chdir("/")
        os.setsid()
        os.umask(0)

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)

        # Start the daemon
        self.daemonize()
        self.run()

    def stop(self):
        """
        Stop the daemon
        """
        try:
            with file(self.pidfile, 'r') as pf:
                pid = int(pf.read().strip())
                os.remove(self.pidfile)
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return

        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            print str(err)
            sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()

    def run(self):
        """
        run
        """


class Counter:
    def __init__(self):
        self.count = random.randint(0, 10000000)

    def get(self):
        self.count += 1
        return self.count


class Client(Counter):
    def __init__(self, mail_info):
        Counter.__init__(self)
        self.session = grequests.Session()
        self.msg_id = self.count
        self.mail_info = mail_info
        self.params = {
            'time': time.time(),
            'appid': '501004106',
            'msgid': '0',
            'clientid': '53999199',
            'ptwebqq': '',
            'vfwebqq': '',
            'psessionid': '',
            'friendList': {},
            'referer2': 'http://s.web2.qq.com/proxy.html?v=20130916001&callback=1&id=1',
            'referer': 'http://d1.web2.qq.com/proxy.html?v=20151105001&callback=1&id=2',
            'smartqqurl': 'http://w.qq.com/login.html'
        }
        self.uin2tuin = 'http://s.web2.qq.com/api/get_friend_uin2?tuin={0}&type=1&vfwebqq={1}&t=1471404618'
        self.session.headers = {
            'Accept': 'application/javascript, */*;q=0.8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/31.0.1650.48 Safari/537.36 QQBrowser/8.2.4258.400'
        }
        self.session.verify = True

    @classmethod
    def get_html_value(cls, content, regex):
        value = re.search(regex, content)
        if value is None:
            return None
        return value.group(1)

    @classmethod
    def combine_msg(cls, content, msg_txt=u""):
        if isinstance(content[1:], list):
            #: item is picture
            for item in content[1:]:
                if isinstance(item, list):
                    if item[0] == 'offpic' or item[0] == 'cface':
                        msg_txt += '[图片]'

                    if item[0] == 'face':
                        msg_txt += '[表情]'
                #判断是否为unicode
                if isinstance(item, unicode):
                    msg_txt += item

        return msg_txt

    def write_msg(self, path, msg, mail=False, content=None):
        if os.path.exists(os.path.split(path)[0]):
            print >> open(path, "a+"), msg
        else:
            raise IOError("error %s" % path)

        if mail and content:
            self.send_mail(content)

    def send_mail(self, content):
        from smtplib import SMTP_SSL as SMTP
        from email.mime.text import MIMEText

        me = "QQSpider<{_user}@{_postfix}>".format(_user=self.mail_info['mail_user'],
                                                   _postfix=self.mail_info['mail_postfix'])
        msg = MIMEText("<h5>QQSpider Error: Number is {0}</h5><br /><span>by QQSpider</span>".format(content),
                       _subtype='html', _charset='utf8')
        msg['Subject'] = "QQSpider Warning"
        msg['From'] = me
        msg['To'] = ";".join(self.mail_info['mail_to_list'].split(','))
        try:
            smtp = SMTP()
            smtp.connect(self.mail_info['mail_host'], self.mail_info['mail_port'])
            smtp.login("{0}@{1}".format(self.mail_info['mail_user'],
                       self.mail_info['mail_postfix']), self.mail_info['mail_pass'])
            smtp.sendmail(me, self.mail_info['mail_to_list'].split(','), msg.as_string())
            smtp.close()
        except Exception as e:
            self.write_msg(self.logs_path, e)
            exit(128)

    def uin_to_account(self, tuin):
        if tuin not in self.params['friendList']:
            try:
                data = self.uin2tuin.format(tuin, self.params['vfwebqq'])
                info = json.loads(self.session.get(data, headers={"Referer": self.params['referer2']}).content)
                if info['retcode'] != 0:
                    raise ValueError(info)

                #: get uin account info
                self.params['friendList'][tuin] = info['result']['account']

            except Exception as e:
                self.write_msg(self.logs_path, e)

        return self.params['friendList'][tuin]

    def save_qrcode(self, filename, url):
        with open(filename, 'wb') as handle:
            response = self.session.get(url, stream=True)
            if not response.ok:
                print "shit"
                exit()

            for block in response.iter_content(1024):
                handle.write(block)

    def up_time(self):
        last_time = (time.time() - self.params['time'])
        self.params['time'] = time.time()
        return str(round(last_time, 3))


class QQ(Client, Daemon):

    def __init__(self, qq_number, logs_path, qrcode_path, data_path, mail_info):
        Client.__init__(self, mail_info=mail_info)
        Daemon.__init__(self, pidfile="/tmp/qq_%s.pid" % qq_number)
        self.count = 0
        self.byebye = 0
        self.try_count = 5
        self.login_err = 1
        self.nickname = None
        self.result = None
        #api 响应超时为 60s ,此处应大于api时间保证得到数据
        self.timeout = 80
        self.qq_number = qq_number
        self.logs_path = logs_path + "/qq_{0}.log".format(qq_number)
        self.data_path = data_path + "/qq_{0}.data".format(qq_number)
        self.orginal_data_path = data_path + "/qq_{0}_orginal.data".format(qq_number)
        self.qrcode_path = qrcode_path + "/qrcode_{0}.png".format(qq_number)
        self.qlogin = 'http://d1.web2.qq.com/channel/login2'
        self.poll2 = 'http://d1.web2.qq.com/channel/poll2'
        self.poll2_data = 'r={{"ptwebqq":"{0}","clientid":{1},"psessionid":"{2}","key":""}}'
        self.qlogin_data = 'r={{"ptwebqq":"{0}","clientid":{1},"psessionid":"{2}","status":"online"}}'
        self.qrcode = 'https://ssl.ptlogin2.qq.com/ptqrshow?appid={_app_id}&e=0&l=M&s=5&d=72&v=4&t=0.3829711841267506'
        self.qrcode_verify = ('https://ssl.ptlogin2.qq.com/ptqrlogin?webqq_type=10&remember_uin=1'
                              '&login2qq=1&aid=501004106&u1=http%3A%2F%2Fw.qq.com%2Fproxy.html%3Flogin2'
                              'qq%3D1%26webqq_type%3D10&ptredirect=0&ptlang=2052&daid=164&from_ui=1'
                              '&pttype=1&dumy=&fp=loginerroralert&action=0-0-{0}&mibao_css={1}'
                              '&t=undefined&g=1&js_type=0&js_ver={2}&login_sig={3}')
    def login(self):
        smartqqurl_content = self.session.get(self.params['smartqqurl']).content
        #self.write_msg(self.logs_path, smartqqurl_content)
        init_url = self.get_html_value(smartqqurl_content, r'\.src = "(.+?)"')
        self.write_msg(self.logs_path, init_url)
        #: login + var name
        _html = self.session.get(init_url + '0').content
        _sign = ''
        _js_ver = '10169'
        _mibao_css = 'm_webqq'
        _start_time = (int(time.mktime(datetime.utcnow().timetuple())) * 1000)

        while True:
            self.count += 1
            self.save_qrcode(self.qrcode_path, self.qrcode.format(_app_id=self.params['appid']))
            while True:
                url = self.qrcode_verify.format(((int(time.mktime(datetime.utcnow().timetuple())) * 1000) - _start_time),_mibao_css, _js_ver, _sign)
                self.write_msg(self.logs_path, url)
                _html = self.session.get(url, headers={"Referer": self.params['referer']}
                ).content
                
                self.result = _html.decode('utf-8').split("'")
                if self.result[1] == '65' or self.result[1] == '0':
                    break

                time.sleep(2)
            
            if self.result[1] == '0' or self.count > 50:
                break

        if self.result[1] != '0':
            raise ValueError("RetCode = %s" % self.result['retcode'])
        #二维码扫描成功
        self.write_msg(self.logs_path, "Login Sucess!")
        #print "Login Sucess"
        self.up_time()
        #: Assignment current nickname
        self.nickname = self.result[11]
        _html = self.session.get(self.result[5]).content
        self.write_msg(self.logs_path, self.result[5])
        self.params['ptwebqq'] = self.session.cookies['ptwebqq']
        
        while self.login_err != 0:
            try:
                '''
                login webqq
                '''
                data=self.qlogin_data.format(self.params['ptwebqq'], self.params['clientid'], self.params['psessionid'])
                _html = self.session.post(self.qlogin,data).content
                self.result = json.loads(_html)
                self.write_msg(self.logs_path, self.result['retcode'])
                if self.result['retcode'] != 0:
                    self.login_err = 1
                else:
                    self.login_err = 0
            except Exception as e:
                self.login_err += 1
                
                self.write_msg(self.logs_path, "Login Field....retrying.... \n{0}".format(e))
                #exit(0)

        if self.result['retcode'] != 0:
            raise ValueError("Login Retcode=%s" % str(self.result['retcode']))
        
        #获得vfwebqq,此处仍有bug,vfwebqq不能争取解析,限定了一个值
        #self.params['vfwebqq'] = self.result['result']['vfwebqq']
        self.params['vfwebqq'] = 'f3a8ac245aa03404de23207a07d40f8a7ac901a2e444d9b597c0a4a64c6430fb'
        #获得psessionid
        self.params['psessionid'] = self.result['result']['psessionid']
        #获得msgid
        self.params['msgid'] = int(random.uniform(20000, 50000))
        
        '''
        
        self.write_msg(self.logs_path, self.params['vfwebqq'])
        
        self.write_msg(self.logs_path, self.params['psessionid'])
        self.params['msgid'] = int(random.uniform(20000, 50000))
        self.write_msg(self.logs_path, self.params['msgid'])
        self.write_msg(self.logs_path, "Login({0}) Sucess, nickname({1})".format(
                       self.result['result']['uin'], self.nickname))
        '''               

    def msg_handler(self, msg):
        try:
            for item in msg:
                msg_type = item['poll_type']
                
                #: message and sess_message no opration
                if msg_type == 'message' or msg_type == 'sess_message':
                    pass

                if msg_type == 'group_message':

                    msg_data = json.dumps(msg,encoding='utf-8')
                    self.write_msg(self.orginal_data_path, msg_data)              
                    uin = item['value']['send_uin']

                    #uid to account
                    try:
                        from_qq_number = self.uin_to_account(uin)
                      
                    except Exception as e:
                        self.write_msg(self.logs_path, "uin2account error!\n{0}".format(e))
                    date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item['value']['time']))
                    text = self.combine_msg(item['value']['content'])
                    str_text=text.encode('gbk')
                    gid = item['value']['group_code']
                    
                    self.write_msg(self.data_path,(date,gid,from_qq_number,self.qq_number,str_text))

 
                if msg_type == 'kick_message':
                    raise Exception(item['value']['reason'])
        except Exception as e:
            self.write_msg(self.logs_path, "msg_handler failed\n{0}".format(e))
            
    def check_message(self):
        try:
            data=self.poll2_data.format(
                self.params['ptwebqq'], self.params['clientid'], self.params['psessionid']
            )
            _html = self.session.post(self.poll2, data, headers={"Referer": self.params['referer']}, timeout=self.timeout).content
            self.write_msg(self.logs_path, _html)
            
        except Exception as _timeout:
            self.write_msg(self.logs_path, "check_message:\n[{0}]".format(_timeout),
                           mail=True, content=self.qq_number)
            self.stop()
        
        self.write_msg(self.logs_path, "Pull message... info[{qq},{time}]".format(
                       qq=self.nickname, time=datetime.now()))
        try:
            result = json.loads(_html,encoding='utf-8')
            self.write_msg(self.logs_path, result)
        except Exception as e:
            self.write_msg(self.logs_path, "Pull message failed, retrying!\n{0}".format(e))
            return self.check_message()

        return result

    def run(self):
        self.login()
        while True:
            time.sleep(0.55)
            if self.byebye < 5:
                result = self.check_message()
            else:
            #出现错误发送邮件提醒
                self.write_msg(self.logs_path, "retcode error", mail=True, content=self.qq_number)
                self.stop()

            #: Post data format error
            if result['retcode'] == 100006:
                self.byebye += 1

            #: No Message
            elif result['retcode'] == 102:
                self.byebye = 0
                
            #: QQ掉线需要重新登陆
            elif result['retcode'] == 100012:
                self.byebye += 1
            
            #: 二次登陆失败,可以先smartQQ网页版登陆一次,再扫描爬虫生成的二维码
            elif result['retcode'] == 103:
                self.byebye += 1

            #: Update ptwebqq value
            elif result['retcode'] == 116:
                self.params['ptwebqq'] = result['p']
                self.byebye = 0
            #: error
            elif result['retcode'] == 0:
                self.write_msg(self.logs_path, "Pull message content!")
                try:
                    self.msg_handler(result['result'])
                except Exception as e:
                    self.write_msg(self.logs_path, "'errmsg': 'error!!!")
                self.byebye = 0
            else:
                self.byebye += 1


if __name__ == '__main__':
    optional = ['start', 'stop', 'restart', 'debug']

    from argparse import ArgumentParser
    parser = ArgumentParser(prog='QQSpider')
    parser.add_argument('--number', required=True, help='qq number')
    parser.add_argument('--action', required=True, help='start|stop|restart|debug')
    args = parser.parse_args()

    if args.action not in optional:
        print "optional error"
        sys.exit(128)

    from ConfigParser import ConfigParser
    CONFIG_PATH = os.environ.get('QQ_CONFIG_PATH') or './config.ini'

    config = ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    else:
        print "CONFIG_PATH error"

    #: create not exists dir
    for _, _path in set(config.items('path')):
        if not os.path.exists(_path):
            os.makedirs(_path)

    daemon = QQ(qq_number=args.number,
                logs_path=config.get('path', 'logs'),
                qrcode_path=config.get('path', 'qrcode'),
                data_path=config.get('path', 'data'),
                mail_info=dict(config.items('smtp')))

    if 'start' == args.action:
        daemon.start()
    elif 'stop' == args.action:
        daemon.stop()
    elif 'restart' == args.action:
        daemon.restart()
    elif 'debug' == args.action:
        daemon.run()
    else:
        print "error"
